{# Après chaque run : la prof peut entrer dans SILVER, GOLD et OPS, la direction uniquement dans GOLD.
   Dans GOLD, ANALYST_ROLE n'a le droit de lire que KPI_FRAUDE_QUOTIDIEN : c'est la démo « accès refusé ». #}
{% macro grant_acces_schemas() %}
    {% if execute and target.type == 'snowflake' %}
        {% for schema in ['SILVER', 'GOLD', 'OPS'] %}
            {% do run_query("create schema if not exists " ~ target.database ~ "." ~ schema) %}
            {% do run_query("grant usage on schema " ~ target.database ~ "." ~ schema ~ " to role REDGRAVE_GRADER") %}
        {% endfor %}
        {% do run_query("grant usage on schema " ~ target.database ~ ".GOLD to role ANALYST_ROLE") %}
        {% do run_query("grant select on table " ~ target.database ~ ".OPS.DBT_RESULTS to role REDGRAVE_GRADER") %}
    {% endif %}
{% endmacro %}
