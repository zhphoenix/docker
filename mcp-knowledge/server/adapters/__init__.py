"""外部系统适配层

当前包含 SiYuan（知识展示层）适配器。所有适配器仅封装对外 API，
不直接读写 PostgreSQL（PG 为唯一 SoT，经 storage 层访问）。
"""