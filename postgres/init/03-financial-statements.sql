-- ============================================================
-- Phase 5: 财务报表深化
-- 三表（利润表/资产负债表/现金流量表）+ 公司基本信息 + 股东
-- ============================================================

-- ============================================================
-- 5.1 financial_income — 利润表
-- ============================================================
CREATE TABLE IF NOT EXISTS financial_income (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market            VARCHAR(10) NOT NULL,
    symbol            VARCHAR(20) NOT NULL,
    year              INTEGER NOT NULL,
    report_type       VARCHAR(20) DEFAULT 'annual',  -- annual/semi/quarter

    -- 营收端
    revenue                  NUMERIC(20,2),   -- 营业总收入
    operating_revenue        NUMERIC(20,2),   -- 营业收入
    interest_income          NUMERIC(20,2),   -- 利息收入（金融类）
    premium_income           NUMERIC(20,2),   -- 保费收入（保险类）

    -- 成本端
    operating_cost           NUMERIC(20,2),   -- 营业成本
    interest_expense         NUMERIC(20,2),   -- 利息支出
    selling_expense          NUMERIC(20,2),   -- 销售费用
    admin_expense            NUMERIC(20,2),   -- 管理费用
    rd_expense               NUMERIC(20,2),   -- 研发费用
    finance_expense          NUMERIC(20,2),   -- 财务费用
    impairment_loss          NUMERIC(20,2),   -- 资产减值损失
    credit_impairment_loss   NUMERIC(20,2),   -- 信用减值损失

    -- 利润端
    gross_profit             NUMERIC(20,2),   -- 毛利润
    operating_profit         NUMERIC(20,2),   -- 营业利润
    total_profit             NUMERIC(20,2),   -- 利润总额
    net_profit               NUMERIC(20,2),   -- 净利润
    net_profit_parent        NUMERIC(20,2),   -- 归母净利润
    deducted_net_profit      NUMERIC(20,2),   -- 扣非净利润

    -- 每股指标
    eps_basic                NUMERIC(12,4),   -- 基本每股收益
    eps_diluted              NUMERIC(12,4),   -- 稀释每股收益

    -- 元数据
    source            VARCHAR(50) DEFAULT 'akshare',
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(market, symbol, year, report_type, source)
);

CREATE INDEX IF NOT EXISTS idx_fi_symbol_year ON financial_income(symbol, year);
CREATE INDEX IF NOT EXISTS idx_fi_market_year ON financial_income(market, year);

-- ============================================================
-- 5.2 financial_balance — 资产负债表
-- ============================================================
CREATE TABLE IF NOT EXISTS financial_balance (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market            VARCHAR(10) NOT NULL,
    symbol            VARCHAR(20) NOT NULL,
    year              INTEGER NOT NULL,
    report_type       VARCHAR(20) DEFAULT 'annual',

    -- 资产端
    cash                       NUMERIC(20,2),   -- 货币资金
    trading_financial_assets   NUMERIC(20,2),   -- 交易性金融资产
    notes_receivable           NUMERIC(20,2),   -- 应收票据
    accounts_receivable        NUMERIC(20,2),   -- 应收账款
    prepayments                NUMERIC(20,2),   -- 预付款项
    inventory                  NUMERIC(20,2),   -- 存货
    non_current_assets_1y      NUMERIC(20,2),   -- 一年内到期非流动资产
    total_current_assets       NUMERIC(20,2),   -- 流动资产合计
    fixed_assets               NUMERIC(20,2),   -- 固定资产
    construction_in_progress   NUMERIC(20,2),   -- 在建工程
    intangible_assets          NUMERIC(20,2),   -- 无形资产
    goodwill                   NUMERIC(20,2),   -- 商誉
    long_term_prepaid_expense  NUMERIC(20,2),   -- 长期待摊费用
    deferred_tax_assets        NUMERIC(20,2),   -- 递延所得税资产
    total_non_current_assets   NUMERIC(20,2),   -- 非流动资产合计
    total_assets               NUMERIC(20,2),   -- 资产总计

    -- 负债端
    short_term_borrowings      NUMERIC(20,2),   -- 短期借款
    notes_payable              NUMERIC(20,2),   -- 应付票据
    accounts_payable           NUMERIC(20,2),   -- 应付账款
    advance_receipts           NUMERIC(20,2),   -- 预收款项/合同负债
    employee_compensation      NUMERIC(20,2),   -- 应付职工薪酬
    tax_payable                NUMERIC(20,2),   -- 应交税费
    other_payables             NUMERIC(20,2),   -- 其他应付款
    total_current_liabilities  NUMERIC(20,2),   -- 流动负债合计
    long_term_borrowings       NUMERIC(20,2),   -- 长期借款
    bonds_payable              NUMERIC(20,2),   -- 应付债券
    total_non_current_liab     NUMERIC(20,2),   -- 非流动负债合计
    total_liabilities          NUMERIC(20,2),   -- 负债合计

    -- 所有者权益
    share_capital              NUMERIC(20,2),   -- 股本
    capital_reserve            NUMERIC(20,2),   -- 资本公积
    surplus_reserve            NUMERIC(20,2),   -- 盈余公积
    retained_earnings          NUMERIC(20,2),   -- 未分配利润
    total_equity_parent        NUMERIC(20,2),   -- 归母所有者权益
    minority_interest          NUMERIC(20,2),   -- 少数股东权益
    total_equity               NUMERIC(20,2),   -- 所有者权益合计

    -- 元数据
    source            VARCHAR(50) DEFAULT 'akshare',
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(market, symbol, year, report_type, source)
);

CREATE INDEX IF NOT EXISTS idx_fb_symbol_year ON financial_balance(symbol, year);
CREATE INDEX IF NOT EXISTS idx_fb_market_year ON financial_balance(market, year);

-- ============================================================
-- 5.3 financial_cashflow — 现金流量表
-- ============================================================
CREATE TABLE IF NOT EXISTS financial_cashflow (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market            VARCHAR(10) NOT NULL,
    symbol            VARCHAR(20) NOT NULL,
    year              INTEGER NOT NULL,
    report_type       VARCHAR(20) DEFAULT 'annual',

    -- 经营活动
    sales_receipts             NUMERIC(20,2),   -- 销售商品收到现金
    tax_refund                   NUMERIC(20,2),   -- 收到税费返还
    other_operating_receipts   NUMERIC(20,2),   -- 收到其他经营活动现金
    total_operating_inflow     NUMERIC(20,2),   -- 经营活动现金流入小计
    purchase_payments          NUMERIC(20,2),   -- 购买商品支付现金
    employee_payments          NUMERIC(20,2),   -- 支付给职工现金
    tax_payments               NUMERIC(20,2),   -- 支付各项税费
    other_operating_payments   NUMERIC(20,2),   -- 支付其他经营活动现金
    total_operating_outflow    NUMERIC(20,2),   -- 经营活动现金流出小计
    net_operating_cashflow     NUMERIC(20,2),   -- 经营活动现金流量净额

    -- 投资活动
    investment_withdrawal      NUMERIC(20,2),   -- 收回投资收到现金
    investment_income          NUMERIC(20,2),   -- 取得投资收益收到现金
    disposal_fixed_assets      NUMERIC(20,2),   -- 处置固定资产收到现金
    total_investing_inflow     NUMERIC(20,2),   -- 投资活动现金流入小计
    investment_payments        NUMERIC(20,2),   -- 投资支付现金
    capex                      NUMERIC(20,2),   -- 购建固定/无形资产支付现金
    total_investing_outflow    NUMERIC(20,2),   -- 投资活动现金流出小计
    net_investing_cashflow     NUMERIC(20,2),   -- 投资活动现金流量净额

    -- 筹资活动
    borrowing_receipts         NUMERIC(20,2),   -- 取得借款收到现金
    total_financing_inflow     NUMERIC(20,2),   -- 筹资活动现金流入小计
    debt_repayment             NUMERIC(20,2),   -- 偿还债务支付现金
    dividend_payments          NUMERIC(20,2),   -- 分配股利/利润/偿付利息
    total_financing_outflow    NUMERIC(20,2),   -- 筹资活动现金流出小计
    net_financing_cashflow     NUMERIC(20,2),   -- 筹资活动现金流量净额

    -- 汇总
    net_cashflow_change        NUMERIC(20,2),   -- 现金及等价物净增加额
    cash_begin                 NUMERIC(20,2),   -- 期初现金余额
    cash_end                   NUMERIC(20,2),   -- 期末现金余额

    -- 元数据
    source            VARCHAR(50) DEFAULT 'akshare',
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(market, symbol, year, report_type, source)
);

CREATE INDEX IF NOT EXISTS idx_fc_symbol_year ON financial_cashflow(symbol, year);
CREATE INDEX IF NOT EXISTS idx_fc_market_year ON financial_cashflow(market, year);

-- ============================================================
-- 5.4 company_basic — 公司基本信息
-- ============================================================
CREATE TABLE IF NOT EXISTS company_basic (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market            VARCHAR(10) NOT NULL,
    symbol            VARCHAR(20) NOT NULL,
    company_name      VARCHAR(200),
    english_name      VARCHAR(300),
    industry          VARCHAR(100),            -- 所属行业
    concept           TEXT,                    -- 概念板块（JSON 数组或逗号分隔）
    list_date         DATE,                    -- 上市日期
    exchange          VARCHAR(50),             -- 交易所（SSE/SZSE/HKEX/NYSE/NASDAQ）
    total_shares      NUMERIC(20,2),           -- 总股本（股）
    float_shares      NUMERIC(20,2),           -- 流通股本（股）
    par_value         NUMERIC(10,4),           -- 每股面值
    registered_capital NUMERIC(20,2),          -- 注册资本
    legal_rep         VARCHAR(100),            -- 法定代表人
    secretary         VARCHAR(100),            -- 董秘
    phone             VARCHAR(100),            -- 公司电话
    website           VARCHAR(300),            -- 公司网站
    email             VARCHAR(200),            -- 公司邮箱
    address           TEXT,                    -- 注册地址
    business_scope    TEXT,                    -- 经营范围
    printer           VARCHAR(200),            -- 会计师事务所
    sponsor           VARCHAR(200),            -- 保荐机构

    source            VARCHAR(50) DEFAULT 'akshare',
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(market, symbol, source)
);

CREATE INDEX IF NOT EXISTS idx_cb_symbol ON company_basic(symbol);
CREATE INDEX IF NOT EXISTS idx_cb_industry ON company_basic(industry);
CREATE INDEX IF NOT EXISTS idx_cb_market ON company_basic(market);

-- ============================================================
-- 5.5 shareholders — 十大股东 / 十大流通股东
-- ============================================================
CREATE TABLE IF NOT EXISTS shareholders (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    market            VARCHAR(10) NOT NULL,
    symbol            VARCHAR(20) NOT NULL,
    year              INTEGER NOT NULL,
    report_type       VARCHAR(20) DEFAULT 'annual',
    holder_type       VARCHAR(20) NOT NULL,    -- top10 / top10_float

    rank              INTEGER NOT NULL,        -- 排名 1-10
    holder_name       VARCHAR(300),            -- 股东名称
    holder_type_desc  VARCHAR(100),            -- 股东类型（个人/机构/国有等）
    hold_shares       NUMERIC(20,2),           -- 持股数量
    hold_pct          NUMERIC(10,4),           -- 持股比例 (%)
    float_shares      NUMERIC(20,2),           -- 流通持股数
    float_pct         NUMERIC(10,4),           -- 流通持股比例 (%)
    change_shares     NUMERIC(20,2),           -- 增减（股）
    change_type       VARCHAR(50),             -- 增减类型（增持/减持/新进/不变）

    source            VARCHAR(50) DEFAULT 'akshare',
    created_at        TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(market, symbol, year, report_type, holder_type, rank, source)
);

CREATE INDEX IF NOT EXISTS idx_sh_symbol_year ON shareholders(symbol, year);
CREATE INDEX IF NOT EXISTS idx_sh_holder ON shareholders(holder_name);
