import pandas as pd

from backend.data import (
    adjustment_quality_checks,
    extract_security_daily_status,
    fetch_akshare_security_master,
    fetch_akshare_dataset,
    filter_to_trading_calendar,
    load_industry_history_csv_text,
    load_dataset_view,
    prepare_market_frame,
)


class FakeAkshare:
    @staticmethod
    def stock_zh_a_hist(**_):
        return pd.DataFrame(
            {
                "日期": ["2024-01-02", "2024-01-03"],
                "股票代码": ["600519", "600519"],
                "名称": ["贵州茅台", "贵州茅台"],
                "开盘": [10.0, 10.2], "收盘": [10.2, 10.5],
                "最高": [10.4, 10.6], "最低": [9.9, 10.1],
                "成交量": [1000, 1200], "成交额": [10200, 12600],
            }
        )

    @staticmethod
    def stock_zh_index_daily_em(**_):
        return pd.DataFrame(
            {
                "date": ["2024-01-02", "2024-01-03"],
                "open": [100.0, 101.0], "close": [101.0, 102.0],
                "high": [102.0, 103.0], "low": [99.0, 100.0],
                "volume": [10000, 12000], "amount": [1_010_000, 1_224_000],
            }
        )

    @staticmethod
    def tool_trade_date_hist_sina():
        return pd.DataFrame({"trade_date": ["2024-01-02", "2024-01-03"]})


class FakeFallbackAkshare(FakeAkshare):
    @staticmethod
    def stock_zh_a_hist(**_):
        raise RuntimeError("eastmoney unavailable")

    @staticmethod
    def stock_zh_a_daily(**_):
        return pd.DataFrame(
            {
                "date": ["2024-01-02", "2024-01-03"],
                "open": [9.8, 10.0], "close": [10.0, 10.3],
                "high": [10.1, 10.4], "low": [9.7, 9.9],
                "volume": [10000, 12000], "amount": [100_000, 123_600],
            }
        )


class FakeSecurityMasterAkshare:
    @staticmethod
    def stock_info_sh_name_code():
        return pd.DataFrame(
            {
                "证券代码": ["600519"],
                "证券简称": ["贵州茅台"],
                "证券全称": ["贵州茅台"],
                "公司简称": ["贵州茅台"],
                "公司全称": ["贵州茅台酒股份有限公司"],
                "上市日期": ["2001-08-27"],
            }
        )

    @staticmethod
    def stock_info_sz_name_code():
        return pd.DataFrame(
            {
                "板块": ["创业板"],
                "A股代码": ["300750"],
                "A股简称": ["宁德时代"],
                "A股上市日期": ["2018-06-11"],
                "A股总股本": ["2,400,000,000"],
                "A股流通股本": ["2,000,000,000"],
                "所属行业": ["C 制造业"],
            }
        )

    @staticmethod
    def stock_info_bj_name_code():
        return pd.DataFrame(
            {
                "证券代码": ["920000"],
                "证券简称": ["安徽凤凰"],
                "总股本": [91680000],
                "流通股本": [57593925],
                "上市日期": ["2020-12-23"],
                "所属行业": ["汽车制造业"],
                "地区": ["安徽省"],
                "报告日期": ["2026-06-23"],
            }
        )

    @staticmethod
    def stock_info_a_code_name():
        return pd.DataFrame(
            {
                "code": ["688001", "600519", "300750"],
                "name": ["华兴源创", "贵州茅台", "宁德时代"],
            }
        )

    @staticmethod
    def stock_info_sh_delist():
        return pd.DataFrame(
            {
                "公司代码": ["600001"],
                "公司简称": ["邯郸钢铁"],
                "上市日期": ["1998-01-22"],
                "暂停上市日期": ["2009-12-29"],
            }
        )

    @staticmethod
    def stock_info_sz_delist():
        return pd.DataFrame(
            {
                "证券代码": ["000003"],
                "证券简称": ["PT金田Ａ"],
                "上市日期": ["1991-01-14"],
                "终止上市日期": ["2002-06-14"],
            }
        )


def test_prepare_market_frame_enriches_reproducibility_fields():
    frame = prepare_market_frame(
        pd.DataFrame(
            {
                "trade_date": ["2024-01-02", "2024-01-03"],
                "symbol": ["300001", "300001"],
                "open": [10, 10.5], "high": [10.8, 11], "low": [9.8, 10.3],
                "close": [10.5, 10.8], "volume": [1000, 1200],
            }
        )
    )
    assert frame.iloc[0]["symbol"] == "300001.SZ"
    assert frame.iloc[1]["prev_close"] == 10.5
    assert frame.iloc[1]["limit_up"] == 12.6
    assert frame.iloc[0]["adjust_factor"] == 1.0
    assert frame.iloc[0]["adjusted_close"] == 10.5
    assert not bool(frame.iloc[0]["suspended"])


def test_adjustment_factor_marks_corporate_actions_and_anomalies():
    frame = prepare_market_frame(
        pd.DataFrame(
            {
                "trade_date": ["2024-01-02", "2024-01-03", "2024-01-04"],
                "symbol": ["600519.SH", "600519.SH", "600519.SH"],
                "open": [10, 10.1, 10.2],
                "high": [10.5, 10.6, 10.7],
                "low": [9.8, 9.9, 10.0],
                "close": [10.0, 10.1, 10.2],
                "volume": [1000, 1000, 1000],
                "adjust_factor": [1.0, 1.1, 2.0],
            }
        )
    )
    assert bool(frame.iloc[1]["corporate_action"])
    assert bool(frame.iloc[2]["adjustment_anomaly"])
    checks = adjustment_quality_checks("dataset-1", frame)
    continuity = [item for item in checks if item["check_name"] == "adjustment_continuity"][0]
    assert continuity["severity"] == "warning"
    assert continuity["details"]["adjustment_anomaly_count"] == 1


def test_dataset_view_is_scoped_by_symbol_and_date(tmp_path):
    frame = fetch_akshare_dataset(
        ["600519.SH"], "2024-01-01", "2024-01-05", client=FakeAkshare
    )
    path = tmp_path / "snapshot.csv"
    frame.to_csv(path, index=False)
    data, benchmark = load_dataset_view(
        path, ["600519.SH"], "2024-01-03", "2024-01-05", "000300.SH"
    )
    assert list(data) == ["600519.SH"]
    assert len(data["600519.SH"]) == 1
    assert len(benchmark) == 1


def test_akshare_adapter_normalizes_stock_index_and_calendar():
    frame = fetch_akshare_dataset(
        ["600519.SH"], "2024-01-01", "2024-01-05", client=FakeAkshare
    )
    assert set(frame["symbol"]) == {"600519.SH", "000300.SH"}
    assert frame[frame["symbol"] == "600519.SH"].iloc[0]["name"] == "贵州茅台"
    assert {"prev_close", "limit_up", "limit_down", "suspended"} <= set(frame.columns)


def test_akshare_adapter_falls_back_to_sina_schema():
    frame = fetch_akshare_dataset(
        ["600519.SH"], "2024-01-01", "2024-01-05", client=FakeFallbackAkshare
    )
    stock = frame[frame["symbol"] == "600519.SH"]
    assert len(stock) == 2
    assert stock.iloc[0]["open"] == 9.8
    assert stock.iloc[0]["name"] == "贵州茅台"


def test_akshare_security_master_normalizes_active_and_delisted_records():
    records = fetch_akshare_security_master(client=FakeSecurityMasterAkshare)
    by_symbol = {record["symbol"]: record for record in records}
    assert by_symbol["600519.SH"]["listed_date"] == "2001-08-27"
    assert by_symbol["688001.SH"]["board"] == "科创板"
    assert by_symbol["300750.SZ"]["board"] == "创业板"
    assert by_symbol["300750.SZ"]["total_share"] == 2_400_000_000
    assert by_symbol["920000.BJ"]["exchange"] == "BJ"
    assert by_symbol["600001.SH"]["status"] == "delisted"
    assert by_symbol["000003.SZ"]["delisted_date"] == "2002-06-14"


def test_limit_rates_cover_st_star_chinext_and_bj():
    frame = prepare_market_frame(
        pd.DataFrame(
            {
                "trade_date": ["2024-01-03"] * 4,
                "symbol": ["600000.SH", "688001.SH", "300001.SZ", "920000.BJ"],
                "name": ["ST浦发", "科创测试", "创业测试", "北交测试"],
                "open": [10, 10, 10, 10],
                "high": [10.5, 12, 12, 13],
                "low": [9.5, 8, 8, 7],
                "close": [10, 10, 10, 10],
                "prev_close": [10, 10, 10, 10],
                "volume": [1000, 1000, 1000, 1000],
            }
        )
    )
    limits = {row["symbol"]: row["limit_up"] for _, row in frame.iterrows()}
    assert limits["600000.SH"] == 10.5
    assert limits["688001.SH"] == 12.0
    assert limits["300001.SZ"] == 12.0
    assert limits["920000.BJ"] == 13.0


def test_ipo_limit_exemptions_are_versioned_by_board_and_listing_date():
    frame = prepare_market_frame(
        pd.DataFrame(
            {
                "trade_date": [
                    "2024-01-02", "2024-01-03",
                    "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09",
                ],
                "symbol": [
                    "920000.BJ", "920000.BJ",
                    "688001.SH", "688001.SH", "688001.SH", "688001.SH", "688001.SH", "688001.SH",
                ],
                "name": ["北交测试", "北交测试", "科创测试", "科创测试", "科创测试", "科创测试", "科创测试", "科创测试"],
                "listed_date": ["2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02", "2024-01-02"],
                "open": [10] * 8,
                "high": [13] * 8,
                "low": [7] * 8,
                "close": [10] * 8,
                "prev_close": [10] * 8,
                "volume": [1000] * 8,
            }
        )
    )
    bj = frame[frame["symbol"] == "920000.BJ"].reset_index(drop=True)
    star = frame[frame["symbol"] == "688001.SH"].reset_index(drop=True)
    assert bool(bj.iloc[0]["limit_exempt"])
    assert not bool(bj.iloc[1]["limit_exempt"])
    assert star.iloc[:5]["limit_exempt"].tolist() == [True] * 5
    assert not bool(star.iloc[5]["limit_exempt"])


def test_pre_registration_main_board_ipo_first_day_uses_special_limit_bounds():
    frame = prepare_market_frame(
        pd.DataFrame(
            {
                "trade_date": ["2022-01-04", "2022-01-05"],
                "symbol": ["600123.SH", "600123.SH"],
                "name": ["主板新股", "主板新股"],
                "listed_date": ["2022-01-04", "2022-01-04"],
                "open": [10, 14.4],
                "high": [14.4, 15.0],
                "low": [6.4, 13.0],
                "close": [14.4, 14.0],
                "prev_close": [10, 14.4],
                "volume": [1000, 1000],
            }
        )
    )
    first_day = frame.iloc[0]
    second_day = frame.iloc[1]
    assert not bool(first_day["limit_exempt"])
    assert first_day["limit_reason"] == "沪深主板注册制前新股上市首日适用44%/-36%特殊价格限制"
    assert first_day["limit_rate"] == 0.44
    assert first_day["limit_up"] == 14.4
    assert first_day["limit_down"] == 6.4
    assert second_day["limit_rate"] == 0.10
    assert second_day["limit_up"] == 15.84


def test_csv_calendar_filter_removes_non_trading_days_with_calendar_client():
    frame = prepare_market_frame(
        pd.DataFrame(
            {
                "trade_date": ["2024-01-02", "2024-01-06"],
                "symbol": ["600519.SH", "600519.SH"],
                "open": [10, 10.2], "high": [10.4, 10.5],
                "low": [9.8, 10.1], "close": [10.2, 10.3],
                "volume": [1000, 1200],
            }
        )
    )
    filtered = filter_to_trading_calendar(
        frame, "2024-01-01", "2024-01-07", client=FakeAkshare
    )
    assert filtered["trade_date"].dt.strftime("%Y-%m-%d").tolist() == ["2024-01-02"]


def test_suspended_string_false_is_not_truthy():
    frame = prepare_market_frame(
        pd.DataFrame(
            {
                "trade_date": ["2024-01-02"],
                "symbol": ["600519.SH"],
                "open": [10], "high": [10.5], "low": [9.8], "close": [10.2],
                "volume": [1000], "suspended": ["False"],
            }
        )
    )
    assert not bool(frame.iloc[0]["suspended"])


def test_industry_history_csv_normalizes_records():
    records = load_industry_history_csv_text(
        "symbol,valid_from,industry,board\n"
        "600519,2001-08-27,食品饮料,沪市主板\n"
        "300750.SZ,2018-06-11,电力设备,\n"
    )
    assert records == [
        {
            "symbol": "300750.SZ",
            "valid_from": "2018-06-11",
            "industry": "电力设备",
            "board": "创业板",
            "source": "industry_history_csv",
        },
        {
            "symbol": "600519.SH",
            "valid_from": "2001-08-27",
            "industry": "食品饮料",
            "board": "沪市主板",
            "source": "industry_history_csv",
        },
    ]


def test_daily_status_marks_long_suspension_after_threshold():
    frame = prepare_market_frame(
        pd.DataFrame(
            {
                "trade_date": pd.bdate_range("2024-01-02", periods=4),
                "symbol": ["600519.SH"] * 4,
                "open": [10, 10, 10, 10],
                "high": [10.5, 10.5, 10.5, 10.5],
                "low": [9.8, 9.8, 9.8, 9.8],
                "close": [10.2, 10.2, 10.2, 10.2],
                "volume": [0, 0, 0, 1000],
            }
        )
    )
    records = extract_security_daily_status(
        "dataset-1", frame, "csv", long_suspension_days=3
    )
    assert [record["suspension_streak"] for record in records] == [1, 2, 3, 0]
    assert records[2]["long_suspended"] is True
    assert records[3]["long_suspended"] is False
