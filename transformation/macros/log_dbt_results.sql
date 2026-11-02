{# Après chaque run : une ligne par modèle ou test dans OPS.DBT_RESULTS (preuve d'exécution, historique, incidents). #}
{% macro log_dbt_results(results) %}
    {% if execute %}
        {% do run_query("create schema if not exists " ~ target.database ~ ".OPS") %}
        {% do run_query(
            "create table if not exists " ~ target.database ~ ".OPS.DBT_RESULTS ("
            ~ "invocation_id varchar, batch_date varchar, node varchar, resource_type varchar, status varchar, "
            ~ "execution_time decimal(10, 3), message varchar, logged_at timestamp)") %}
        {% for r in results %}
            {% set message = (r.message or '') | string | replace("'", "''") %}
            {% do run_query(
                "insert into " ~ target.database ~ ".OPS.DBT_RESULTS values ('"
                ~ invocation_id ~ "', '" ~ (var('batch_date') or '') ~ "', '" ~ r.node.name ~ "', '"
                ~ r.node.resource_type ~ "', '" ~ r.status ~ "', " ~ (r.execution_time or 0) ~ ", '"
                ~ message[:500] ~ "', current_timestamp)") %}
        {% endfor %}
    {% endif %}
{% endmacro %}
