# Support Ticket Intelligence — powered by Snowflake Cortex

A small Snowflake-native demo that loads support ticket text, enriches it with Cortex classification and sentiment, creates semantic ticket search, and exposes the workflow in Streamlit in Snowflake.

## Architecture

```text
CSV files
  -> Snowflake internal stages
  -> RAW_SUPPORT_TICKETS and TICKET_METADATA
  -> SUPPORT_TICKET_INTELLIGENCE
  -> AI_CLASSIFY, AI_SENTIMENT, Cortex Search, Cortex Analyst
  -> Streamlit in Snowflake
```


## Demo Flow

Use the Agent Search tab to search tickets by meaning, such as:

```text
late delivery problem
```

Use the Manager Analytics tab to ask:

```text
Which issue category has the lowest satisfaction rating?
How long does it take on average to resolve a billing issue?
Which channel has the most unresolved tickets?
```
