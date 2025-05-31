# Databricks notebook source
# MAGIC %sql
# MAGIC SELECT * FROM careconnect.default.users;

# COMMAND ----------

# MAGIC %sql
# MAGIC USE CATALOG careconnect;
# MAGIC USE SCHEMA default;

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE TABLE IF NOT EXISTS users (
# MAGIC     user_id STRING,
# MAGIC     first_name STRING,
# MAGIC     last_name STRING,
# MAGIC     age INT,
# MAGIC     gender STRING,
# MAGIC     email STRING,
# MAGIC     if_pregnant BOOLEAN
# MAGIC )
# MAGIC USING DELTA;
# MAGIC

# COMMAND ----------

# MAGIC %sql
# MAGIC CREATE TABLE IF NOT EXISTS medical_conditions (
# MAGIC     condition_id STRING,
# MAGIC     user_id STRING,
# MAGIC     condition_name STRING,
# MAGIC     diagnosis_date DATE,
# MAGIC     is_chronic BOOLEAN,
# MAGIC     notes STRING
# MAGIC )
# MAGIC USING DELTA;
# MAGIC

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT * FROM careconnect.default.medical_conditions;
# MAGIC

# COMMAND ----------

# MAGIC %sql 
# MAGIC SELECT 
# MAGIC   STATE,
# MAGIC   COUNT(*) AS hospital_count
# MAGIC FROM careconnect.default.all_india_hospital_list
# MAGIC GROUP BY STATE
# MAGIC ORDER BY hospital_count DESC;

# COMMAND ----------

# MAGIC %md
# MAGIC # SQl agent 

# COMMAND ----------

system_message = """You are an intelligent SQL assistant for a healthcare data analytics platform running inside Databricks notebooks.

Your job is to translate user questions into **pure SQL queries** that are ready to run in `%sql` cells inside Databricks.

### Available Tables
The following tables are available in Unity Catalog under catalog `careconnect` and schema `default`.

1. Table: `careconnect.default.all_india_hospital_list`
   - Columns:
     - Hospital Name (string)
     - Address (string)
     - CITY (string)
     - STATE (string)
     - PIN CODE (string)
     - PPN / NON PPN (string)
   - Description: Contains hospital information across India, useful for analyzing location, type (PPN/NON PPN), and accessibility of hospitals.

2. Table: `careconnect.default.medical_conditions`
   - Columns:
     - condition_id (string)
     - user_id (string)
     - condition_name (string)
     - diagnosis_date (date)
     - is_chronic (boolean)
     - notes (string)
   - Description: Contains medical condition records for users, including diagnosis date and chronic status. 

3. Table: `careconnect.default.users`
   - Columns:
     - user_id (string)
     - first_name (string)
     - last_name (string)
     - age (bigint)
     - gender (string)
     - email (string)
     - if_pregnant (boolean)
   - Description: Contains information about individual users including demographics and health status. It supports tracking patient details and tailoring healthcare services.

### Important Relationships
- The `user_id` column in the `users` table uniquely identifies each user.
- The `medical_conditions` table can have multiple rows per user because a user may have multiple medical conditions. Thus, `user_id` in `medical_conditions` is not unique.
- Each row in `medical_conditions` is uniquely identified by the `condition_id` column.
- Use these relationships to join tables when answering questions involving both users and their medical conditions.

### Rules:
- Only generate **pure SQL queries** that will be executed in a `%sql` cell in a Databricks notebook.
- Use **fully qualified table names** as listed above.
- Do not explain the query.
- Always wrap the SQL in triple backticks (```).
- Use `LIMIT` in queries that return large result sets.
- Make intelligent assumptions if some information is missing or unclear.

Respond only with the SQL code block, and nothing else.

"""

# COMMAND ----------

from openai import OpenAI

DATABRICKS_TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

client = OpenAI(
    api_key=DATABRICKS_TOKEN,
    base_url="https://dbc-65fcd381-2e74.cloud.databricks.com/serving-endpoints"
)

def generate_sql_from_question(question):
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": question}
    ]
    
    response = client.chat.completions.create(
        model="databricks-claude-3-7-sonnet",
        messages=messages
    )
    
    content = response.choices[0].message.content
    sql_code = content.split("```")[1].strip() if "```" in content else content
    return sql_code

def ask_and_run(question):
    sql_query = generate_sql_from_question(question)
    sql_query= sql_query.replace("sql",'') + ";"
    try:
        df = spark.sql(sql_query)
        return df
    except Exception as e:
        print("Failed to run SQL:\n", e)

# COMMAND ----------

# MAGIC %md
# MAGIC # Expensive task run with patient 

# COMMAND ----------

question = "HOSPICAL IN DELHI"
# ask_and_run(question)
sql_query = generate_sql_from_question(question)
sql_query= sql_query.replace("sql",'') + ";"
df = spark.sql(sql_query)


# COMMAND ----------

sql_query

# COMMAND ----------

pandas_df = df.toPandas()
dict_result = pandas_df.to_dict(orient="records")
dict_result

# COMMAND ----------


