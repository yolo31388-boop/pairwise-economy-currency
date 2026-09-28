"""货币与经济系统 - 红态测试"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from economy.currency import Economy

class TestExchangeFee:
    def test_exchange_has_fee_no_arbitrage(self):
        eco = Economy()
        eco.wallets["p1"] = {"A": 1000, "B": 0}
        eco.exchange_rate["A_B"] = 1.0
        eco.exchange_rate["B_A"] = 1.0
        eco.exchange_fee = 0.1  # 10%手续费
        eco.exchange("p1", "A", "B", 100)
        eco.exchange("p1", "B", "A", 90)
        # 往返后应该有损耗，不能回到1000
        assert eco.wallets["p1"]["A"] < 1000  # bug1: 还是1000

class TestMarketPriceCap:
    def test_listing_price_has_cap(self):
        eco = Economy()
        result = eco.list_item("p1", "white_item", 10**9)
        assert result == False  # bug2: 返回True

class TestMailAtomic:
    def test_mail_claim_is_atomic(self):
        eco = Economy()
        eco.wallets["p1"] = {"gold": 0}
        eco.mail_attachments["m1"] = [
            {"currency": "gold", "amount": 100, "claimed": False},
            {"currency": "gold", "amount": 200, "claimed": False},
        ]
        # 模拟第一个成功第二个失败（这里简化：直接验证标记和给币一致）
        eco.claim_mail_attachment("m1", 0, "p1")
        assert eco.wallets["p1"]["gold"] == 100
        assert eco.mail_attachments["m1"][0]["claimed"] == True
        # 如果第二个失败，第一个应该回滚
        # 这里验证原子性：失败时不改变状态
        eco.mail_attachments["m1"][1]["claimed"] = True  # 模拟已领
        before = eco.wallets["p1"]["gold"]
        result = eco.claim_mail_attachment("m1", 1, "p1")
        assert result == False
        assert eco.wallets["p1"]["gold"] == before  # bug3: 可能重复给

class TestBuybackLimit:
    def test_buyback_has_limit(self):
        eco = Economy()
        for i in range(60):
            eco.add_buyback({"id": i})
        assert len(eco.buyback_list) <= 50  # bug4: 60个

class TestLevelScaling:
    def test_daily_reward_scales_with_level(self):
        eco = Economy()
        r1 = eco.get_daily_reward(1)
        r60 = eco.get_daily_reward(60)
        assert r60 > r1  # bug5: 都是100

class TestCoinOverflow:
    def test_transfer_checks_overflow(self):
        eco = Economy()
        eco.wallets["p1"] = {"gold": 100}
        eco.wallets["p2"] = {"gold": 2**31 - 50}  # 接近上限
        result = eco.transfer("p1", "p2", 100)
        assert result == False  # bug6: 溢出变成负数
        assert eco.wallets["p2"]["gold"] <= 2**31 - 1
