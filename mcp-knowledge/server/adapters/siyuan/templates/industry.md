# {{ name }}（行业）

{% if description %}
{{ description }}
{% endif %}

## 行业概览
{% for s in sections %}
### {{ s.title }}
{{ s.content }}
{% else %}
_（暂无内容）_
{% endfor %}

## 相关实体
{% for r in related_entities %}- [[{{ r.name }}]]（{{ r.relation_type }}）
{% else %}_（暂无关联）_{% endfor %}

---
*由 AI 投研平台自动渲染 · 数据源: PostgreSQL (SoT)*