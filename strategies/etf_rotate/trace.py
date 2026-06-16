# encoding:gbk
'''
API获取信号交易
'''
import json
import os
import pandas as pd
import time
import datetime
import requests
import xml.etree.ElementTree as ET
from xml.dom import minidom


def init(ContextInfo):
    """
    初始化上下文信息，包括基础URL、认证码、运行时间和打印频率。
    """
    ContextInfo.base_url = "http://trader.igateway.cn"
    # ContextInfo.base_url = "http://localhost:8888"
    create_custom_xml_file(ContextInfo, '聚宽跟单_API_V3')
    # 授权码
    ContextInfo.auth_code = auth_code
    # 下单比例
    ContextInfo.trade_weight = order_ratio
    # 账户设置
    ContextInfo.acct_type = 'stock'
    ContextInfo.account = account
    ContextInfo.set_account(account)
    # 最后一次同步持仓的时间戳
    ContextInfo.last_sync_time = 0
    # 最后一次撤销超时委托的时间戳
    ContextInfo.last_cancel_timeout_orders = 0
    # 订单超时撤单时间
    ContextInfo.order_cancel_timeout = int(order_cancel_timeout[:-2])
    # 交易执行频率
    ContextInfo.exec_interval = int(exec_interval[:-1])
    # 日志打印频率
    ContextInfo.print_interval = int(print_interval[:-1])
    # 是否开启测试  开启测试不校验当前是不是交易时间
    ContextInfo.open_test = open_test
    # 定期执行
    ContextInfo.run_time("execute_task", f"{ContextInfo.exec_interval}nSecond", "2019-10-14 13:20:00")
    ContextInfo.signal_check_counter = 0
    ContextInfo.order_list = []
    ContextInfo.status_map = {49: "待报", 50: "已报", 51: "已报待撤", 52: "部成待撤", 53: "部撤", 54: "已撤",
                              55: "部成", 56: "已成", 57: "废单"}
    cancel_order(ContextInfo)


def execute_task(ContextInfo):
    """
    任务执行函数
    """
    if is_trade_time(ContextInfo) or ContextInfo.open_test == '开启':
        # 获取信号
        fetch_trade_signal(ContextInfo)
        # 执行交易
        execute_trades(ContextInfo)
        # 定期撤单
        cancel_timeout_order(ContextInfo)
        # 重新挂单
        relist_unfilled_orders(ContextInfo)


def is_trade_time(ContextInfo):
    """
    检查是否交易时间
    """
    now = datetime.datetime.now()
    current_time = now.time()
    weekday = now.weekday()  # 0-4 是周一到周五
    # 检查是否为交易日（周一至周五，非节假日）
    if weekday >= 5:  # 周六、周日
        # "非交易时段（周末休市）"
        return False
    # 定义交易时段
    trading_periods = [
        {"name": "开盘集合竞价", "start": "09:15:00", "end": "09:25:00", "can_cancel": True},
        {"name": "早盘连续竞价", "start": "09:30:00", "end": "11:30:00", "can_cancel": True},
        {"name": "午间休市", "start": "11:30:00", "end": "13:00:00", "can_cancel": False},
        {"name": "午盘连续竞价", "start": "13:00:00", "end": "14:57:00", "can_cancel": True},
        {"name": "收盘集合竞价", "start": "14:57:00", "end": "15:00:00", "can_cancel": False},
    ]
    # 科创板和创业板的盘后交易（15:05-15:30）
    kechuang_cyb_period = {"name": "科创/创业板盘后交易", "start": "15:05:00", "end": "15:30:00", "can_cancel": False}
    # 检查当前是否在交易时段
    for period in trading_periods:
        start_time = datetime.datetime.strptime(period["start"], "%H:%M:%S").time()
        end_time = datetime.datetime.strptime(period["end"], "%H:%M:%S").time()
        if start_time <= current_time <= end_time:
            return True
    # 检查是否在科创/创业板盘后交易时段
    kechuang_start = datetime.datetime.strptime(kechuang_cyb_period["start"], "%H:%M:%S").time()
    kechuang_end = datetime.datetime.strptime(kechuang_cyb_period["end"], "%H:%M:%S").time()
    if kechuang_start <= current_time <= kechuang_end:
        return True
    # 不在任何交易时段
    return False


def relist_unfilled_orders(ContextInfo):
    # 分离出已撤的信号
    signals = [signal for signal in ContextInfo.order_list if signal['订单状态'] == "已撤"]
    for signal in signals:
        change_signal_status(ContextInfo, signal, '待报')


def execute_trades(ContextInfo):
    """
    执行所有待报的交易信号。
    """
    # 分离出待报的信号
    unreported_signals = [signal for signal in ContextInfo.order_list if signal['订单状态'] == "待报"]
    # 执行卖出
    sell_signals = [signal for signal in unreported_signals if signal['买卖方向'] == '卖出']
    for signal in sell_signals:
        flag, updated_signal = qmt_sell_check(ContextInfo, signal)
        if flag:
            passorder(24, 1101, ContextInfo.account, updated_signal['证券代码'], 5, 0, updated_signal['下单数量'],
                      '聚宽跟单', 2, updated_signal['订单编号'], ContextInfo)
    # 执行买入
    buy_signals = [signal for signal in unreported_signals if signal['买卖方向'] == '买入']
    for signal in buy_signals:
        flag, updated_signal = qmt_buy_check(ContextInfo, signal)
        if flag:
            passorder(23, 1101, ContextInfo.account, updated_signal['证券代码'], 5, 0, updated_signal['下单数量'],
                      "聚宽跟单", 1, updated_signal['订单编号'], ContextInfo)


def qmt_sell_check(ContextInfo, signal):
    """
    检查卖出信号的有效性。
    如果可用数量小于卖出数量 则卖出数量=可用数量
    """
    # 验证是否重复订单
    if prevent_duplicate_orders(ContextInfo, signal):
        return False, signal
    price = signal['下单价格']
    # 获取标的持仓
    position_dict = get_position(ContextInfo).get(signal['证券代码'])
    if position_dict is None:
        print(f"\n【信息】 [卖出校验] 可用数量不足，标的不存在: {signal['证券代码']}")
        change_signal_status(ContextInfo, signal, '废单')
        return False, signal

    available_volume = position_dict['available_volume']
    if signal['下单数量'] > available_volume:
        print(f"\n【信息】 [卖出校验] 可用数量：{available_volume:.2f} 实际数量：{signal['下单数量']:.2f}")
        signal['下单数量'] = available_volume
        if available_volume == 0:
            change_signal_status(ContextInfo, signal, '废单')
            return False, signal
    return True, signal


def qmt_buy_check(ContextInfo, signal):
    """
    检查买入信号的有效性。
    """
    # 验证是否重复订单
    if prevent_duplicate_orders(ContextInfo, signal):
        return False, signal

    price = signal['下单价格']
    buy_amount = signal['下单数量'] * price
    account_info = get_trade_detail_data(ContextInfo.account, ContextInfo.acct_type, 'account')[0]
    available_funds = account_info.m_dAvailable
    if buy_amount > available_funds:
        # 计算理论上的最大股数
        max_quantity = available_funds / price
        # 确保股数是100的倍数（向下取整）
        max_quantity = (int(max_quantity / 100)) * 100
        print(
            f"\n【信息】 [买入校验] 可用金额：{available_funds:.2f} 买入金额：{buy_amount:.2f}  最大可买数量：{max_quantity:.2f}")
        signal['下单数量'] = max_quantity
        if max_quantity == 0:
            change_signal_status(ContextInfo, signal, '废单')
            return False, signal
    return True, signal


def prevent_duplicate_orders(ContextInfo, signal):
    """
    防止重复订单
    """
    orderId = signal['订单编号']
    orders = get_deal_orders(ContextInfo)
    if orderId in orders:
        if orders[orderId]['status'] == 56:
            # print(f"\n【信息】 [重复订单] 订单编号： {orderId} 证券代码：{orders[orderId]['stock_code']}  买卖方向：{orders[orderId]['action']} 下单数量：{orders[orderId]['amount']} 完成时间：{orders[orderId]['order_time']}")
            # signal['下单价格'] = round(orders[orderId]['price'], 3)
            # change_signal_status(ContextInfo, signal, '已成')
            return True
        elif orders[orderId]['status'] in [50, 51, 52, 53, 55]:
            # print(f"\n【信息】 [重复委托] 订单编号： {orderId} 证券代码：{orders[orderId]['stock_code']}  买卖方向：{orders[orderId]['action']} 下单数量：{orders[orderId]['amount']} 委托时间：{orders[orderId]['order_time']}")
            # change_signal_status(ContextInfo, signal, '已报')
            return True
        else:
            return False
    else:
        return False


def cancel_timeout_order(ContextInfo):
    """撤销超时未成交的委托"""
    current_dt = pd.Timestamp('now')  # 获取当前时间
    orders = get_pending_orders(ContextInfo)  # 获取当前未完成委托
    if not isinstance(orders, dict):
        return  # 如果未完成委托不是字典类型，直接返回
    for stock_code, order in orders.items():
        order_time = order['order_time']  # 获取委托时间
        orderid = order['order_id']  # 获取委托单 ID
        my_order_id = order['my_order_id']  # 获取委托单 ID
        stock = stock_code  # 标的代码
        flag = can_cancel_order(orderid, ContextInfo.account, 'stock')
        # print('撤单检测：', order_time, (current_dt - pd.Timestamp(order_time) > pd.Timedelta(minutes=ContextInfo.order_cancel_timeout)), can_cancel_order(orderid, ContextInfo.account, 'stock'))
        # 检查委托单是否超时（5 分钟）并且可以撤销   and can_cancel_order(orderid, ContextInfo.accountID, 'stock')
        if (current_dt - pd.Timestamp(order_time) > pd.Timedelta(
                minutes=ContextInfo.order_cancel_timeout)) and can_cancel_order(orderid, ContextInfo.account, 'stock'):
            signal = get_order_by_order_id(ContextInfo, my_order_id)
            if not signal:
                # print(f"\n【警告】未找到订单编号为 {my_order_id} 的信号")
                return
            cancel(orderid, ContextInfo.account, 'stock', ContextInfo)  # 撤销委托单


def cancel_order(ContextInfo):
    """撤销未成交的委托"""
    current_dt = pd.Timestamp('now')  # 获取当前时间
    orders = get_pending_orders(ContextInfo)  # 获取当前未完成委托
    if not isinstance(orders, dict):
        return  # 如果未完成委托不是字典类型，直接返回
    for stock_code, order in orders.items():
        order_time = order['order_time']  # 获取委托时间
        orderid = order['order_id']  # 获取委托单 ID
        my_order_id = order['my_order_id']  # 获取委托单 ID
        stock = stock_code  # 标的代码
        flag = can_cancel_order(orderid, ContextInfo.account, 'stock')
        if can_cancel_order(orderid, ContextInfo.account, 'stock'):
            signal = get_order_by_order_id(ContextInfo, my_order_id)
            if not signal:
                # print(f"\n【警告】未找到订单编号为 {my_order_id} 的信号")
                return
            cancel(orderid, ContextInfo.account, 'stock', ContextInfo)  # 撤销委托单


def get_pending_orders(ContextInfo):
    """
    获取账户中的未完成委托
    跳过无效委托单 跳过数量等于0的委托单 跳过已完成或者已撤销的
    """
    orders = get_trade_detail_data(ContextInfo.account, 'STOCK', 'ORDER')
    pending_orders = {}
    for order in list(orders):
        if not order or order == "":
            continue  # 跳过无效委托单
        amount = order.m_nVolumeTotal  # 委托单的总数量
        action = '买入' if order.m_nOffsetFlag == 48 else '卖出'
        if amount <= 0:
            continue  # 跳过数量不大于 0 的委托单

        status = order.m_nOrderStatus
        if status not in [54, 56]:  # 状态 54 和 56 为已完成或撤销状态，跳过
            stock_code = f"{order.m_strInstrumentID}.{order.m_strExchangeID}"
            order_dict = {  # 创建委托单信息字典
                "order_id": order.m_strOrderSysID,
                "action": action,
                "stock_code": stock_code,
                "amount": amount,
                "my_order_id": order.m_strRemark,
                "order_time": f"{order.m_strInsertDate}{order.m_strInsertTime}"
            }
            pending_orders[stock_code] = order_dict
    return pending_orders


def get_deal_orders(ContextInfo):
    """
    获取账户中的已完成订单
    跳过无效委托单 跳过数量等于0的委托单
    """
    orders = get_trade_detail_data(ContextInfo.account, 'STOCK', 'ORDER')
    deal_orders = {}
    for order in list(orders):
        if not order or order == "":
            continue  # 跳过无效委托单
        amount = order.m_nVolumeTotal  # 委托单的总数量
        action = '买入' if order.m_nOffsetFlag == 48 else '卖出'

        status = order.m_nOrderStatus
        stock_code = f"{order.m_strInstrumentID}.{order.m_strExchangeID}"
        order_dict = {  # 创建委托单信息字典
            "order_id": order.m_strRemark,
            "action": action,
            "status": status,
            "stock_code": stock_code,
            "amount": amount,
            "price": order.m_dTradedPrice,
            "order_time": f"{order.m_strInsertDate}{order.m_strInsertTime}"
        }
        deal_orders[order.m_strRemark] = order_dict
    return deal_orders


def orderError_callback(ContextInfo, orderArgs, errMsg):
    print(f"\n【警告】{errMsg}")


def order_callback(ContextInfo, orderInfo):
    """
    委托主推函数
    """
    signal = get_order_by_order_id(ContextInfo, orderInfo.m_strRemark)
    if not signal:
        # print(f"\n【警告】未找到订单编号为 {orderInfo.m_strRemark} 的信号")
        return
    print(f'\n【信息】 [委托主推]  订单编号：{orderInfo.m_strRemark} 股票代码:  {orderInfo.m_strInstrumentID} ',
          f'证券名称: {orderInfo.m_strInstrumentName}  买卖方向: {signal["买卖方向"]} ',
          f'委托数量: {orderInfo.m_nVolumeTotalOriginal:.2f}  成交均价: {orderInfo.m_dTradedPrice:.2f}',
          f'状态: {ContextInfo.status_map.get(orderInfo.m_nOrderStatus, "未知状态")} ')
    if orderInfo.m_nOrderStatus == 56:
        signal['下单价格'] = round(orderInfo.m_dTradedPrice, 3)
    change_signal_status(ContextInfo, signal, ContextInfo.status_map.get(orderInfo.m_nOrderStatus, "未知状态"))


def get_order_by_order_id(ContextInfo, order_id):
    """
    根据订单编号获取信号对象。
    """
    for order in ContextInfo.order_list:
        if order['订单编号'] == order_id:
            return order
    return None


def change_signal_status(ContextInfo, order, new_status):
    """
    根据订单编号变更信号的状态。
    """
    order_id = order.get('订单编号')
    if order_id is None:
        print("【警告】信号缺少订单ID，无法变更状态:", order)
        return
    # 查找匹配的信号
    for item in ContextInfo.order_list:
        if item['订单编号'] == order_id and new_status != item['订单状态']:
            old_status = item['订单状态']
            item['订单状态'] = new_status
            print(
                f"\n【信息】 [状态变更] 订单编号： {order_id} 证券代码：{item['证券代码']}  买卖方向：{item['买卖方向']} 下单数量：{item['下单数量']}  订单状态:[{old_status} -> {new_status}]")
            if new_status in ('已成', '废单'):
                push_order_status(ContextInfo, item)
            break


def push_order_status(ContextInfo, order):
    """
    推送订单状态 避免订单重复执行
    """
    payload = {
        "authCode": ContextInfo.auth_code,
        "orderId": order['订单编号'],
        "qmtOrderStatus": '已成交',
        "remarks": '',
        "price": order['下单价格']
    }
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.post(ContextInfo.base_url + '/api/open/v1/pushOrderStatus', headers=headers,
                             data=json.dumps(payload))
    if response.status_code == 200:
        print("\n【信息】 [状态推送]", order)
    else:
        print("\n【订单状态】推送失败:", response.status_code, response.text)


def get_position(ContextInfo):
    """
    获取持仓信息。
    """
    position_list = get_trade_detail_data(ContextInfo.account, ContextInfo.acct_type, 'position')
    position_dict = {
        i.m_strInstrumentID + '.' + i.m_strExchangeID: {
            "total_volume": int(i.m_nVolume),  # 总持仓量
            "available_volume": int(i.m_nCanUseVolume)  # 可用持仓量
        }
        for i in position_list
    }
    return position_dict


def fetch_trade_signal(ContextInfo):
    """
    从API获取交易信号，并处理响应数据。
    每print_interval秒打印一次“【信息】等待聚宽调仓信号...”。
    """
    ContextInfo.signal_check_counter += 1
    payload = {"authCode": ContextInfo.auth_code}
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(
            f"{ContextInfo.base_url}/api/open/v1/pullJoinQuantOrder",
            headers=headers,
            data=json.dumps(payload)
        )
        if response.status_code == 200:
            response_data = response.json()
            if response_data['code'] == 200:
                signal_list = response_data['data']
                if not signal_list:
                    # 每print_interval秒打印一次等待信号的消息
                    if ContextInfo.signal_check_counter % ContextInfo.print_interval == 0:
                        print("【信息】 [获取信号] 等待聚宽调仓信号...")
                else:
                    for signal in signal_list:
                        merge_signal(ContextInfo, signal)
                return signal_list or []
            else:
                print("【错误】[获取信号] 调仓信号获取失败:", response_data['msg'])
        else:
            print("【错误】[获取信号]调仓信号获取失败:", response.status_code, response.text)
    except requests.RequestException as e:
        print(f"【错误】[获取信号]请求发生异常: {e}")
    if ContextInfo.signal_check_counter % ContextInfo.print_interval == 0:
        ContextInfo.signal_check_counter = 0
    return []


def merge_signal(ContextInfo, signal):
    """
    合并新的交易信号，检查订单ID是否唯一，并将其添加到已知信号列表中。
    为新信号添加订单状态字段，并根据交易权重调整下单数量。
    """
    # print(f'订单列表：{ContextInfo.order_list}')
    orderId = signal.get('orderId')
    # print(f'已有订单：{order_id}')
    if any(s['订单编号'] == orderId for s in ContextInfo.order_list):
        pass
    else:
        original_amount = signal.get('amount')
        scaled_amount = int(original_amount * ContextInfo.trade_weight)
        scaled_amount = (scaled_amount // 100) * 100
        orders = get_deal_orders(ContextInfo)
        if scaled_amount >= 100:
            # if orderId not in orders:
            signal_with_status = {}
            signal_with_status['订单编号'] = signal.get('orderId')
            signal_with_status['证券代码'] = signal.get('security')
            signal_with_status['买卖方向'] = signal.get('buySell')
            signal_with_status['下单价格'] = signal.get('price')
            signal_with_status['下单数量'] = scaled_amount
            signal_with_status['订单状态'] = "待报"
            print(
                f"\n【信息】 [信号接收] 订单编号： {signal.get('orderId')} 证券代码：{signal.get('security')}  买卖方向：{signal.get('buySell')} 下单数量：{scaled_amount}")
            ContextInfo.order_list.append(signal_with_status)
        else:
            print(f"\n【警告】调整后的下单数量无效: {scaled_amount}, 必须大于等于100")


def print_notice(ContextInfo, filename):
    type_part, version_part = filename.split("_", 1)
    payload = {
        "type": type_part,
        "version": version_part
    }
    headers = {
        'Content-Type': 'application/json'
    }
    try:
        response = requests.post(ContextInfo.base_url + '/api/open/v1/notice/getLastNotice', headers=headers,
                                 data=json.dumps(payload))
        if response.status_code == 200:
            response_data = response.json()
            if response_data['code'] == 200:
                data = response_data['data']
                if data['content'] is None:
                    print(f'【警告】 请登录知识星球下载最新版本 当前版本即将停用!!!\n' * 20)
                    ContextInfo.print_interval = 1000000
                else:
                    print(f"\n{data['content']}")
            else:
                print("【错误】[获取使用教程] 获取使用教程失败:", response_data['msg'])
        else:
            print("【错误】[获取使用教程]获取使用教程失败:", response.status_code, response.text)
    except requests.RequestException as e:
        print(f"【错误】[获取使用教程]请求发生异常: {e}")


# 策略初始化成功
def create_custom_xml_file(ContextInfo, filename):
    version_name = filename
    filename = filename + '.xml'
    target_dir = "python/formulaLayout"

    def prettify(element):
        rough_string = ET.tostring(element, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="\t")

    root = ET.Element("TCStageLayout")
    control = ET.SubElement(root, "control", attrib={"note": "控件"})
    variable = ET.SubElement(control, "variable", attrib={"note": "控件"})
    items = [
        {
            "position": "",
            "bind": "auth_code",
            "value": "",
            "note": "授权码",
            "name": "授权码",
            "type": "input"
        },
        {
            "position": "",
            "bind": "order_ratio",
            "value": "1",
            "note": "QMT下单比例",
            "name": "QMT下单比例",
            "type": "input"
        },
        {
            "position": "",
            "comboType": "exec_interval",
            "list": "1秒,5秒,30秒,60秒",
            "bind": "exec_interval",
            "value": "1秒",
            "note": "执行频率",
            "name": "执行频率",
            "type": "combo"
        },
        {
            "position": "",
            "comboType": "order_cancel_timeout",
            "list": "1分钟,5分钟,30分钟,60分钟",
            "bind": "order_cancel_timeout",
            "value": "5分钟",
            "note": "超时撤单时间",
            "name": "超时撤单时间",
            "type": "combo"
        },
        {
            "position": "",
            "comboType": "print_interval",
            "list": "1秒,5秒,30秒,60秒,180秒,300秒,600秒,1800秒",
            "bind": "print_interval",
            "value": "1秒",
            "note": "日志频率",
            "name": "日志频率",
            "type": "combo"
        },
        {
            "position": "",
            "comboType": "open_test",
            "list": "开启,关闭",
            "bind": "open_test",
            "value": "关闭",
            "note": "开启测试",
            "name": "开启测试",
            "type": "combo"
        }
    ]
    for item_data in items:
        ET.SubElement(variable, "item", attrib=item_data)
    formatted_xml = prettify(root)
    current_directory = os.getcwd()
    parent_directory = os.path.dirname(current_directory)
    target_directory = os.path.join(parent_directory, target_dir)
    os.makedirs(target_directory, exist_ok=True)
    full_path = os.path.join(target_directory, filename)
    with open(full_path, "w", encoding="utf-8") as file:
        file.write(formatted_xml)
    print(f"【初始化】策略初始化成功")
    print_notice(ContextInfo, version_name)


