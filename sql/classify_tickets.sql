USE ROLE ACCOUNTADMIN;
USE WAREHOUSE SUPPORT_INTELLIGENCE_WH;
USE DATABASE SUPPORT_INTELLIGENCE;
USE SCHEMA SUPPORT_OPS;

-- Classify tickets into the demo support categories.
UPDATE SUPPORT_TICKET_INTELLIGENCE AS target
SET PREDICTED_CATEGORY = classification.PREDICTED_CATEGORY
FROM (
  SELECT
    TICKET_ID,
    AI_CLASSIFY(
      TICKET_TEXT,
      [
        'Billing',
        'Shipping Delay',
        'Product Defect',
        'Account Access',
        'Returns',
        'General Enquiry'
      ]
    ):labels[0]::VARCHAR AS PREDICTED_CATEGORY
  FROM SUPPORT_TICKET_INTELLIGENCE
  WHERE TICKET_TEXT IS NOT NULL
    AND PREDICTED_CATEGORY IS NULL
) AS classification
WHERE target.TICKET_ID = classification.TICKET_ID
  AND classification.PREDICTED_CATEGORY IS NOT NULL;
