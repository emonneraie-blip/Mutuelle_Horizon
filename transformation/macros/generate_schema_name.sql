{# Écrit dans SILVER, GOLD et OPS, sans préfixe. Même macro que le TD. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}{{ target.schema }}{%- else -%}{{ custom_schema_name | trim | upper }}{%- endif -%}
{%- endmacro %}
