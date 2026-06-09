"""
Agent 工具集 — LangChain @tool 装饰器
create_agent 通过 tools 参数绑定这些工具到 Agent
"""
import json
from langchain.tools import tool


@tool
def search_rag(query: str) -> str:
    """
    检索金融政策文档和合规标准。
    当需要查询投资政策法规、风控指引、合规标准时使用。
    """
    policy_db = {
        "债券": "《债券投资管理办法》第12条：单一债券投资不得超过净资产的5%。"
               "信用债投资需经风控审批。",
        "股票": "《股票投资风控指引》第3条：单只股票持仓不超过基金资产的10%。"
               "创业板、ST股票投资需额外合规审查。投资金额超500万需投委会审批。",
        "基金": "《基金投资合规审查标准》第8条：QDII基金需外管局额度审批。",
        "风控": "风控红线：1) 单一标的集中度<=10% 2) VaR<=2% "
               "3) 杠杆率<=140% 4) 流动性覆盖率>=100%",
        "合规": "合规要点：1) 内幕信息核查 2) 关联交易申报 "
               "3) 反洗钱审查 4) 信息披露义务 5) 适当性匹配",
    }
    for key, content in policy_db.items():
        if key in query:
            return f"[政策依据] {content}"
    return f"未找到与'{query}'直接匹配的政策，通用风控要求：{policy_db['风控']}"


@tool
def query_financial_db(query_type: str, symbol: str = "", amount: float = 0) -> str:
    """
    查询财务数据库。获取标的的财务数据、估值、舆情或历史波动。
    参数:
      - query_type: "基本面" / "估值" / "舆情" / "历史波动"
      - symbol: 标的名称，如"贵州茅台"或"600519"
      - amount: 投资金额(万元)
    """
    mock_data = {
        ("基本面", "贵州茅台"): {"symbol": "600519", "pe": 28.5, "pb": 8.2,
                              "roe": "30.1%", "revenue_growth": "15.3%",
                              "debt_ratio": "21.4%", "rating": "AAA"},
        ("估值", "贵州茅台"): {"current_price": 1680, "target_price": 1950,
                            "upside": "16.1%", "current_pe": 28.5,
                            "pe_5y_avg": 32.0, "valuation": "合理偏低"},
        ("舆情", "贵州茅台"): {"positive_ratio": 0.65, "negative_ratio": 0.12,
                            "key_concerns": ["消费降级影响", "渠道改革不确定"],
                            "recent_events": ["Q3财报超预期"]},
        ("历史波动", "贵州茅台"): {"annual_volatility": "22.5%",
                                "max_drawdown": "-35%", "sharpe_ratio": 1.15,
                                "var_95": "-2.8%"},
    }
    key = (query_type, symbol)
    if key in mock_data:
        return json.dumps(mock_data[key], ensure_ascii=False)
    return json.dumps({"error": f"未找到{symbol}的{query_type}数据"}, ensure_ascii=False)


@tool
def sentiment_analysis(topic: str, days: int = 7) -> str:
    """
    舆情情感分析。了解市场情绪时使用。
    参数:
      - topic: 标的名称
      - days: 回溯天数
    """
    mock = {
        "贵州茅台": {"sentiment_score": 0.72, "trend": "上升",
                    "hot_words": ["业绩超预期", "提价预期", "消费复苏"],
                    "institution_opinion": "80%券商给予买入/增持评级"},
    }
    result = mock.get(topic, {"sentiment_score": 0.5, "trend": "中性",
                               "hot_words": [], "institution_opinion": "暂无数据"})
    return json.dumps(result, ensure_ascii=False)


# 工具注册表 — create_agent 用
ALL_TOOLS = [search_rag, query_financial_db, sentiment_analysis]


if __name__ == "__main__":
    print("=" * 50)
    print("工具测试")
    print("=" * 50)

    print("\n[1] search_rag('股票'):")
    print("  ", search_rag.invoke({"query": "股票"}))

    print("\n[2] query_financial_db(基本面, 贵州茅台):")
    print("  ", query_financial_db.invoke({"query_type": "基本面", "symbol": "贵州茅台"}))

    print("\n[3] sentiment_analysis(贵州茅台):")
    print("  ", sentiment_analysis.invoke({"topic": "贵州茅台"}))

    print(f"\n[OK] {len(ALL_TOOLS)} 个工具就绪")
