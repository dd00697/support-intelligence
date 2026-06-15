from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st
from snowflake.snowpark.context import get_active_session


DATABASE = "SUPPORT_INTELLIGENCE"
SCHEMA = "SUPPORT_OPS"
SEARCH_SERVICE = "SUPPORT_TICKET_SEARCH_SERVICE"
SEMANTIC_MODEL_FILE = (
    "@SUPPORT_INTELLIGENCE.SUPPORT_OPS.SEMANTIC_MODEL_STAGE/"
    "ticket_metadata_semantic_model.yaml"
)
ANALYST_ENDPOINT = "/api/v2/cortex/analyst/message"
API_TIMEOUT_MS = 50000
APP_TITLE = "Support Ticket Intelligence"


st.set_page_config(page_title=APP_TITLE, layout="wide")
session = get_active_session()


def run_sql(sql: str) -> pd.DataFrame:
    return session.sql(sql).to_pandas()


def escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def parse_json_payload(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return {}


def sentiment_label(score: Any) -> str:
    if score is None or pd.isna(score):
        return "Not scored"
    numeric_score = float(score)
    if numeric_score <= -0.5:
        return "Negative"
    if numeric_score >= 0.5:
        return "Positive"
    return "Neutral"


def compact_text(value: Any, max_length: int = 180) -> str:
    text = "" if value is None else str(value).strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3].rstrip()}..."


def normalize_search_results(results: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for result in results:
        normalized = {str(key).upper(): value for key, value in result.items()}
        sentiment = normalized.get("SENTIMENT")
        rows.append(
            {
                "Ticket ID": normalized.get("TICKET_ID"),
                "Ticket preview": compact_text(normalized.get("TICKET_TEXT")),
                "Predicted category": normalized.get("PREDICTED_CATEGORY"),
                "Sentiment": sentiment_label(sentiment),
                "Sentiment score": sentiment,
                "Search score": normalized.get("@SEARCH.SCORE")
                or normalized.get("SCORE")
                or normalized.get("_SCORE"),
                "Satisfaction": normalized.get("SATISFACTION_RATING"),
                "Channel": normalized.get("CHANNEL"),
                "Product line": normalized.get("PRODUCT_LINE"),
            }
        )
    return pd.DataFrame(rows)


def query_cortex_search(search_text: str, limit: int) -> pd.DataFrame:
    request = {
        "query": search_text,
        "columns": [
            "TICKET_ID",
            "TICKET_TEXT",
            "PREDICTED_CATEGORY",
            "SENTIMENT",
            "SATISFACTION_RATING",
            "CHANNEL",
            "PRODUCT_LINE",
        ],
        "limit": limit,
    }
    request_json = escape_sql_literal(json.dumps(request))
    service_name = f"{DATABASE}.{SCHEMA}.{SEARCH_SERVICE}"
    rows = run_sql(
        f"""
        SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
          '{service_name}',
          '{request_json}'
        ) AS SEARCH_RESPONSE
        """
    )
    payload = parse_json_payload(rows.iloc[0]["SEARCH_RESPONSE"])
    return normalize_search_results(payload.get("results", []))


def call_cortex_analyst(question: str) -> dict[str, Any]:
    import _snowflake

    request_body = {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": question}],
            }
        ],
        "semantic_model_file": SEMANTIC_MODEL_FILE,
    }
    response = _snowflake.send_snow_api_request(
        "POST",
        ANALYST_ENDPOINT,
        {},
        {},
        request_body,
        None,
        API_TIMEOUT_MS,
    )
    payload = parse_json_payload(response.get("content", {}))
    status_code = int(response.get("status", 500))
    if status_code >= 400:
        message = payload.get("message", "Cortex Analyst request failed.")
        raise RuntimeError(message)

    answer_parts: list[str] = []
    generated_sql: str | None = None
    for part in payload.get("message", {}).get("content", []):
        if part.get("type") == "text":
            answer_parts.append(part.get("text", ""))
        if part.get("type") == "sql":
            generated_sql = part.get("statement")

    result_data = run_sql(generated_sql) if generated_sql else pd.DataFrame()
    return {
        "answer": "\n\n".join(answer_parts).strip(),
        "sql": generated_sql,
        "data": result_data,
    }


def get_unresolved_by_channel() -> pd.DataFrame:
    return run_sql(
        """
        SELECT
          CHANNEL,
          COUNT(*) AS UNRESOLVED_TICKETS
        FROM SUPPORT_TICKET_INTELLIGENCE
        WHERE CHANNEL IS NOT NULL
          AND RESOLVED_AT IS NULL
        GROUP BY CHANNEL
        ORDER BY UNRESOLVED_TICKETS DESC
        """
    )


def render_agent_search() -> None:
    st.subheader("Search tickets by meaning")
    search_text = st.text_input(
        "Search tickets by meaning",
        value="late delivery problem",
        label_visibility="collapsed",
    )
    limit = st.slider("Results", min_value=5, max_value=25, value=10, step=5)

    if not st.button("Search tickets", type="primary"):
        return

    if not search_text.strip():
        st.warning("Enter a search phrase.")
        return

    try:
        results = query_cortex_search(search_text.strip(), limit)
    except Exception as exc:
        st.error(
            "Cortex Search is not available. Create "
            f"`{SEARCH_SERVICE}` before running this tab."
        )
        st.code(str(exc))
        return

    if results.empty:
        st.info("No tickets matched this search.")
        return

    st.dataframe(results, use_container_width=True, hide_index=True)


def render_manager_analytics() -> None:
    st.subheader("Ask a question about support operations")

    st.markdown("#### Unresolved tickets by channel")
    unresolved = get_unresolved_by_channel()
    st.bar_chart(unresolved.set_index("CHANNEL")["UNRESOLVED_TICKETS"])

    question = st.text_input("Manager question")

    if not st.button("Ask question", type="primary"):
        return

    if not question.strip():
        st.warning("Enter a manager question.")
        return

    try:
        result = call_cortex_analyst(question.strip())
    except Exception as exc:
        st.error(
            "Cortex Analyst is not available. Upload the semantic model YAML "
            "to `SEMANTIC_MODEL_STAGE` before running this tab."
        )
        st.code(str(exc))
        return

    if not result["data"].empty:
        st.dataframe(result["data"], use_container_width=True, hide_index=True)


def main() -> None:
    st.title(APP_TITLE)
    agent_search_tab, manager_analytics_tab = st.tabs(
        ["Agent Search", "Manager Analytics"]
    )

    with agent_search_tab:
        render_agent_search()

    with manager_analytics_tab:
        render_manager_analytics()


if __name__ == "__main__":
    main()
