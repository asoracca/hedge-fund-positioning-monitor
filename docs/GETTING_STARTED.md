# Your first five minutes

You do not need finance experience or Python knowledge to explore the dashboard
once it is running. Installing and hosting it requires a basic Python setup.

## Run it

From the repository folder, follow the README installation commands and run
`streamlit run app.py`. A local page opens at `http://localhost:8501`.
GitHub hosts the code; it does not automatically host this Python application.
For a shareable web app, follow [the deployment guide](DEPLOYMENT.md).

## Explore in this order

1. **Overview:** see which generated managers and sectors dominate disclosed value.
   These are sample observations, not real fund holdings.
2. **Holdings explorer:** search `Alder`, choose a quarter, and inspect its positions.
   Compare the previous quarter to see new disclosures, exits and share changes.
3. **Crowding monitor:** inspect each component of a high-scoring security. Change
   one sidebar weight and observe how the ranking changes.
4. **Manager network:** raise the similarity threshold to retain only the most
   similar portfolios. An edge means shared exposure, not collaboration.
5. **Signal research:** increase costs from 15 to 50 basis points and observe the
   effect on net returns. Keep the date cutoff fixed when comparing experiments.

## Plain-language glossary

| Term | Meaning |
|---|---|
| 13F | A delayed disclosure of certain institutional securities holdings |
| CIK | SEC identifier for a filing entity; an issuer and its investors have different CIKs |
| Crowding | Multiple investors exposed to the same security; this app uses an exploratory score |
| HHI | Sum of squared weights; higher means more concentrated |
| Cosine similarity | Similarity of two managers' relative portfolio weights |
| IC | Rank correlation between a signal and later returns; it can be negative |
| Drawdown | Decline from a portfolio's previous peak |
| Basis point | 0.01 percentage point; 15 bps is 0.15% per dollar traded |
| Look-ahead bias | Using information that was not yet available when a decision was made |

## Can you use it yourself?

Yes: for learning, portfolio research workflows, coding practice, interviews and
reproducible experiments. The included dataset is synthetic, so it cannot tell
you what actual hedge funds hold or which stocks to buy. The code does not place
trades or connect to brokerage accounts.

To study actual institutions, load SEC filings, historical security mappings and
authorized total-return prices using [the real-data pipeline](DEPLOYMENT.md).
That stage requires more data skills and careful review. Read the methodology
before interpreting any result. A high crowding score is not a buy recommendation.
