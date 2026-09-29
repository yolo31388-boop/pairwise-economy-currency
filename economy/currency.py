"""货币与经济系统（修复版）。

修复内容：
1. 兑换收取固定比例手续费，保证往返兑换必有损耗；
2. 交易行上架价格有上下限，且与物品等级/品质挂钩；
3. 邮件附件领取使用事务，全成功或全回滚；
4. 回购列表只保留最近 50 条，按时间倒序排列；
5. 每日任务金币奖励按玩家等级区间缩放；
6. 金币以 64 位整数口径校验，交易前先校验溢出风险。
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1

# 各品质物品的上架价格基数（金币），再乘以物品等级得到上限
_RARITY_BASE_CAP = {
    "white": 1_000,
    "green": 10_000,
    "blue": 100_000,
    "purple": 1_000_000,
    "orange": 10_000_000,
}
_DEFAULT_BASE_CAP = _RARITY_BASE_CAP["white"]
MARKET_PRICE_MIN = 1

# 每日奖励的等级区间：(等级上限（含）, 金币奖励)
_LEVEL_REWARD_BANDS = (
    (10, 100),
    (20, 200),
    (30, 350),
    (40, 500),
    (50, 750),
    (60, 1000),
)
_MAX_LEVEL = 60


@dataclass
class Currency:
    name: str
    amount: int = 0


def _is_plain_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class Economy:
    def __init__(self):
        self.wallets: dict[str, dict[str, int]] = {}  # player -> {currency: amount}
        self.exchange_rate: dict[str, int] = {}  # "A_B" -> rate（整数汇率）
        self.exchange_fee: float = 0.0  # 兑换手续费比例，如 0.1 表示 10%
        self.market_listings: list[dict] = []
        self.mail_attachments: dict[str, list[dict]] = {}  # mail_id -> [{currency, amount, claimed}]
        self.buyback_list: list[dict] = []
        self.max_buyback = 50
        # 单角色金币持有上限（业务上限保持不变；底层按 64 位整数校验）
        self.coin_cap: int = 2**31 - 1

    # ---------- 通用内部工具 ----------

    @staticmethod
    def _check_int64(value: int) -> bool:
        return _is_plain_int(value) and INT64_MIN <= value <= INT64_MAX

    def _credit(self, player: str, currency: str, amount: int) -> bool:
        """给玩家增加货币；校验 64 位范围，金币额外校验持有上限。"""
        if not _is_plain_int(amount) or amount <= 0:
            return False
        wallet = self.wallets.setdefault(player, {})
        current = wallet.get(currency, 0)
        new_amount = current + amount
        if not self._check_int64(new_amount):
            return False
        if currency == "gold" and new_amount > self.coin_cap:
            return False
        wallet[currency] = new_amount
        return True

    # ---------- 1. 货币兑换（固定比例手续费） ----------

    def exchange(self, player: str, from_cur: str, to_cur: str, amount: int) -> bool:
        if player not in self.wallets:
            return False
        if not _is_plain_int(amount) or amount <= 0:
            return False
        if self.wallets[player].get(from_cur, 0) < amount:
            return False

        rate = self.exchange_rate.get(f"{from_cur}_{to_cur}", 1)
        try:
            rate_frac = rate if isinstance(rate, Fraction) else Fraction(str(rate))
        except (ValueError, TypeError):
            return False
        if rate_frac <= 0:
            return False

        fee_rate = self.exchange_fee
        try:
            fee_frac = fee_rate if isinstance(fee_rate, Fraction) else Fraction(str(fee_rate))
        except (ValueError, TypeError):
            return False
        if fee_frac < 0 or fee_frac >= 1:
            return False

        # 用精确分数运算，避免浮点误差；手续费保证不低于名义比例
        gross_frac = Fraction(amount) * rate_frac
        gross = gross_frac.numerator // gross_frac.denominator
        received_frac = gross_frac * (Fraction(1) - fee_frac)
        received = received_frac.numerator // received_frac.denominator
        if gross <= 0 or not self._check_int64(gross):
            return False
        if received <= 0 or not self._check_int64(received):
            return False

        # 先校验到账后的上限/范围，再扣款，避免半途失败
        target_balance = self.wallets[player].get(to_cur, 0) + received
        if not self._check_int64(target_balance):
            return False
        if to_cur == "gold" and target_balance > self.coin_cap:
            return False

        self.wallets[player][from_cur] -= amount
        self.wallets[player][to_cur] = target_balance
        return True

    # ---------- 2. 交易行上架（价格上下限 + 物品等级挂钩） ----------

    @staticmethod
    def _parse_item(item) -> tuple[str, int]:
        """解析物品的 (品质, 等级)。

        支持 dict（{"name"/"item"/"id": ..., "rarity"/"quality": ..., "level": ...}）
        和字符串（前缀即品质，如 "white_item"）。缺省按 1 级白装处理。
        """
        if isinstance(item, dict):
            name = item.get("name", item.get("item", item.get("id", "")))
            rarity = str(item.get("rarity", item.get("quality", "white"))).lower()
            level = item.get("level", 1)
        else:
            name = str(item)
            head = name.split("_", 1)[0].lower() if name else ""
            rarity = head if head in _RARITY_BASE_CAP else "white"
            level = 1

        if not _is_plain_int(level):
            level = 1
        level = max(1, min(level, _MAX_LEVEL))
        return rarity, level

    def _market_price_cap(self, item) -> int:
        rarity, level = self._parse_item(item)
        base = _RARITY_BASE_CAP.get(rarity, _DEFAULT_BASE_CAP)
        return base * level

    def list_item(self, player: str, item: str, price: int, *, item_level: int | None = None) -> bool:
        if not _is_plain_int(price):
            return False
        if item_level is not None:
            if isinstance(item, dict):
                item = dict(item)
                item.setdefault("level", item_level)
            elif not isinstance(item, dict):
                item = {"name": str(item), "level": item_level}

        price_cap = self._market_price_cap(item)
        if price < MARKET_PRICE_MIN or price > price_cap:
            return False

        rarity, level = self._parse_item(item)
        self.market_listings.append(
            {
                "seller": player,
                "item": item,
                "rarity": rarity,
                "item_level": level,
                "price": price,
            }
        )
        return True

    # ---------- 3. 邮件附件领取（事务：全成功或全回滚） ----------

    def claim_mail_attachment(self, mail_id: str, idx: int, player: str) -> bool:
        if mail_id not in self.mail_attachments:
            return False
        atts = self.mail_attachments[mail_id]
        if not _is_plain_int(idx) or idx < 0 or idx >= len(atts):
            return False
        if atts[idx].get("claimed"):
            return False

        attachment = atts[idx]
        amount = attachment.get("amount")
        currency = attachment.get("currency")
        if not _is_plain_int(amount) or amount <= 0 or not isinstance(currency, str):
            return False

        self.wallets.setdefault(player, {})
        wallet_snapshot = dict(self.wallets[player])
        try:
            if not self._credit(player, currency, amount):
                raise ValueError("credit failed")
            # 标记与加币在同一事务内；任何异常都回滚
            atts[idx]["claimed"] = True
        except Exception:
            self.wallets[player] = wallet_snapshot
            return False
        return True

    # ---------- 4. 商店回购列表（最近 50 条，时间倒序） ----------

    def add_buyback(self, item: dict):
        # 头插即最新在前；列表始终按时间倒序
        self.buyback_list.insert(0, item)
        if len(self.buyback_list) > self.max_buyback:
            del self.buyback_list[self.max_buyback:]

    # ---------- 5. 每日任务奖励（按等级区间缩放） ----------

    def get_daily_reward(self, player_level: int) -> int:
        if not _is_plain_int(player_level) or player_level < 1:
            return _LEVEL_REWARD_BANDS[0][1]
        if player_level > _MAX_LEVEL:
            return _LEVEL_REWARD_BANDS[-1][1]
        for upper_level, reward in _LEVEL_REWARD_BANDS:
            if player_level <= upper_level:
                return reward
        return _LEVEL_REWARD_BANDS[-1][1]

    # ---------- 6. 金币转账（64 位整数 + 交易前溢出/上限校验） ----------

    def transfer(self, from_p: str, to_p: str, amount: int) -> bool:
        if from_p not in self.wallets or to_p not in self.wallets:
            return False
        if not _is_plain_int(amount) or amount <= 0:
            return False

        sender_balance = self.wallets[from_p].get("gold", 0)
        if sender_balance < amount:
            return False

        receiver_balance = self.wallets[to_p].get("gold", 0)
        new_receiver = receiver_balance + amount
        new_sender = sender_balance - amount

        # 交易前校验：64 位范围、单角色金币上限、扣款后余额合法
        if not self._check_int64(new_receiver) or not self._check_int64(new_sender):
            return False
        if new_receiver > self.coin_cap:
            return False
        if new_sender < 0:
            return False

        # 全部校验通过后才改状态，转账本身也是原子的
        self.wallets[from_p]["gold"] = new_sender
        self.wallets[to_p]["gold"] = new_receiver
        return True
