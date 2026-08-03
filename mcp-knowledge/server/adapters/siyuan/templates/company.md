# {{ name }}
{{ "\n" }}
{% if ticker %}**代码**: `{{ ticker }}`{% if market %} · **市场**: {{ market }}{% endif %}{{ "\n" }}{% endif %}
{% if entity_type %}**类型**: {{ entity_type }}{{ "\n" }}{% endif %}
{% if description %}
{{ description }}
{% endif %}

{% if aliases %}
**别名**: {% for a in aliases %}`{{ a }}`{% if not loop.last %}, {% endif %}{% endfor %}
{% endif %}

## 概览
{% for s in sections %}
### {{ s.title }}
{{ s.content }}
{% else %}
_（暂无内容）_
{% endfor %}

---
*由 AI 投研平台自动渲染 · 数据源: PostgreSQL (SoT) · 置信度 {{ confidence | conf }}*