{% test in_range(model, column_name, min, max) %}
-- tiny range check instead of pulling in the dbt_utils package
select * from {{ model }} where {{ column_name }} < {{ min }} or {{ column_name }} > {{ max }}
{% endtest %}
