-- Les règles de nettoyage : écrites une fois, utilisées dans tous les modèles (spécification : validate.py).

{# '', 'N/A', 'null' et '-' deviennent NULL #}
{% macro clean_text(col) -%}
    case when upper(trim({{ col }})) in ('', 'N/A', 'NULL', '-') then null else trim({{ col }}) end
{%- endmacro %}

{# '074 789 535 205 83' -> '07478953520583' #}
{% macro clean_digits(col) -%}
    regexp_replace({{ clean_text(col) }}, '[^0-9]', '')
{%- endmacro %}

{# ' simple ', 'Tres_Complexe' -> 'SIMPLE', 'TRES_COMPLEXE' #}
{% macro clean_code(col) -%}
    upper(replace({{ clean_text(col) }}, ' ', '_'))
{%- endmacro %}

{# 2026-10-21, 21/10/2026, 20261021 -> une vraie date. Une date impossible (31/02) devient NULL #}
{% macro clean_date(col) -%}
    coalesce(
        try_to_date({{ clean_text(col) }}, 'YYYY-MM-DD'),
        try_to_date({{ clean_text(col) }}, 'DD/MM/YYYY'),
        try_to_date({{ clean_text(col) }}, 'YYYYMMDD'))
{%- endmacro %}

{# '90,20', '1 234,50 €' -> 1234.50 #}
{% macro clean_amount(col) -%}
    try_to_number(replace(regexp_replace({{ clean_text(col) }}, '[^0-9,.-]', ''), ',', '.'), 12, 2)
{%- endmacro %}

{# Le sel rend l'empreinte impossible à retrouver en essayant tous les NIR possibles #}
{% macro hash_nir(col) -%}
    sha2('{{ env_var("NIR_SALT", "") }}' || {{ clean_digits(col) }}, 256)
{%- endmacro %}

{# La date du lot traité : celle donnée par Airflow, sinon le dernier lot de factures #}
{% macro batch_date() -%}
    {%- if var('batch_date') -%}
        cast('{{ var("batch_date") }}' as date)
    {%- else -%}
        (select max(batch_date) from {{ ref('slv_factures') }})
    {%- endif -%}
{%- endmacro %}
