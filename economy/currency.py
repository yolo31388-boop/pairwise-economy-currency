"""货币与经济系统 - 含6个bug"""
from dataclasses import dataclass, field
import struct

@dataclass
class Currency:
    name: str
    amount: int = 0

class Economy:
    def __init__(self):
        self.wallets: dict[str, dict[str, int]] = {}  # player -> {currency: amount}
        self.exchange_rate: dict[str, float] = {}  # "A_B" -> rate
        self.exchange_fee: float = 0.0  # bug1: 无手续费
        self.market_listings: list[dict] = []
        self.mail_attachments: dict[str, list[dict]] = {}  # mail_id -> [{currency, amount, claimed}]
        self.buyback_list: list[dict] = []
        self.max_buyback = 50
        self.coin_cap = 2**31 - 1  # bug6: 32位有符号

    def exchange(self, player: str, from_cur: str, to_cur: str, amount: int) -> bool:
        # bug1: 无手续费，可套利
        if player not in self.wallets:
            return False
        if self.wallets[player].get(from_cur, 0) < amount:
            return False
        rate = self.exchange_rate.get(f"{from_cur}_{to_cur}", 1.0)
        received = int(amount * rate)
        self.wallets[player][from_cur] -= amount
        self.wallets[player][to_cur] = self.wallets[player].get(to_cur, 0) + received
        return True

    def list_item(self, player: str, item: str, price: int) -> bool:
        # bug2: 价格无上限
        self.market_listings.append({"seller": player, "item": item, "price": price})
        return True

    def claim_mail_attachment(self, mail_id: str, idx: int, player: str) -> bool:
        # bug3: 领取无原子性，领了一半掉线附件没了
        if mail_id not in self.mail_attachments:
            return False
        atts = self.mail_attachments[mail_id]
        if idx >= len(atts) or atts[idx]["claimed"]:
            return False
        atts[idx]["claimed"] = True
        # 先标记再给货币，如果中间失败就丢了
        self.wallets.setdefault(player, {})
        self.wallets[player][atts[idx]["currency"]] = self.wallets[player].get(atts[idx]["currency"], 0) + atts[idx]["amount"]
        return True

    def add_buyback(self, item: dict):
        # bug4: 回购列表无数量限制
        self.buyback_list.append(item)

    def get_daily_reward(self, player_level: int) -> int:
        # bug5: 奖励不按等级缩放
        return 100

    def transfer(self, from_p: str, to_p: str, amount: int) -> bool:
        # bug6: 32位整数溢出
        if from_p not in self.wallets or to_p not in self.wallets:
            return False
        if self.wallets[from_p].get("gold", 0) < amount:
            return False
        self.wallets[from_p]["gold"] -= amount
        new_amount = self.wallets[to_p].get("gold", 0) + amount
        # bug6续: 不检查溢出
        self.wallets[to_p]["gold"] = new_amount
        return True
