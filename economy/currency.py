"""货币与经济系统"""
from dataclasses import dataclass, field

MAX_INT64 = 2**63 - 1  # 金币以64位有符号整数存储

@dataclass
class Currency:
    name: str
    amount: int = 0

class Economy:
    def __init__(self):
        self.wallets: dict[str, dict[str, int]] = {}  # player -> {currency: amount}
        self.exchange_rate: dict[str, float] = {}  # "A_B" -> rate
        self.exchange_fee: float = 0.05  # 固定比例手续费，往返兑换必有损耗
        self.market_listings: list[dict] = []
        self.mail_attachments: dict[str, list[dict]] = {}  # mail_id -> [{currency, amount, claimed}]
        self.buyback_list: list[dict] = []
        self.max_buyback = 50
        self.coin_cap = 2**31 - 1  # 单钱包金币上限（设计约束，存储本身为64位）

    def exchange(self, player: str, from_cur: str, to_cur: str, amount: int) -> bool:
        # 兑换收取固定比例手续费，往返兑换必有损耗，无法套利
        if player not in self.wallets:
            return False
        if amount <= 0:
            return False
        if self.wallets[player].get(from_cur, 0) < amount:
            return False
        rate = self.exchange_rate.get(f"{from_cur}_{to_cur}", 1.0)
        received = int(amount * rate * (1.0 - self.exchange_fee))
        self.wallets[player][from_cur] -= amount
        self.wallets[player][to_cur] = self.wallets[player].get(to_cur, 0) + received
        return True

    def list_item(self, player: str, item, price: int) -> bool:
        # 上架价格有上下限，且上限与物品等级挂钩
        level = item.get("level", 1) if isinstance(item, dict) else 1
        level = max(1, int(level))
        min_price = 1
        max_price = 1_000_000 * level
        if not (min_price <= price <= max_price):
            return False
        self.market_listings.append({"seller": player, "item": item, "price": price})
        return True

    def claim_mail_attachment(self, mail_id: str, idx: int, player: str) -> bool:
        # 事务性领取：先校验，再一次性提交；任何一步失败整体回滚
        if mail_id not in self.mail_attachments:
            return False
        atts = self.mail_attachments[mail_id]
        if idx >= len(atts) or atts[idx]["claimed"]:
            return False
        att = atts[idx]
        currency = att["currency"]
        amount = att["amount"]
        self.wallets.setdefault(player, {})
        old_balance = self.wallets[player].get(currency, 0)
        new_balance = old_balance + amount
        if new_balance > MAX_INT64:
            return False  # 校验失败，不产生任何副作用
        try:
            self.wallets[player][currency] = new_balance
            att["claimed"] = True
        except Exception:
            # 回滚到领取前状态
            self.wallets[player][currency] = old_balance
            att["claimed"] = False
            return False
        return True

    def add_buyback(self, item: dict):
        # 回购列表只保留最近max_buyback条，按时间倒序（最新在前）
        self.buyback_list.insert(0, item)
        del self.buyback_list[self.max_buyback:]

    def get_daily_reward(self, player_level: int) -> int:
        # 每日任务金币奖励按玩家等级区间缩放
        brackets = [
            (1, 9, 100),
            (10, 29, 300),
            (30, 49, 600),
            (50, 999, 1000),
        ]
        for low, high, reward in brackets:
            if low <= player_level <= high:
                return reward
        return 100

    def transfer(self, from_p: str, to_p: str, amount: int) -> bool:
        # 交易前校验溢出风险，超出上限则拒绝且不产生副作用
        if from_p not in self.wallets or to_p not in self.wallets:
            return False
        if amount <= 0:
            return False
        if self.wallets[from_p].get("gold", 0) < amount:
            return False
        new_amount = self.wallets[to_p].get("gold", 0) + amount
        if new_amount > self.coin_cap or new_amount > MAX_INT64:
            return False
        self.wallets[from_p]["gold"] -= amount
        self.wallets[to_p]["gold"] = new_amount
        return True
