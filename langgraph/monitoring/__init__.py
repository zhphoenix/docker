"""Watchlist Monitoring Engine — 自选股智能监控

提供每日监控主流程、每日报告生成、告警通知（Web + 通用 Webhook）。
复用现有 news 采集管线（api.news::_run_collection）与 news 查询服务（services.news_storage）。
"""