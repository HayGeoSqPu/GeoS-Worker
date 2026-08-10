# GeoS-Worker
```
my_fastapi_app/
├── app/
│   ├── api/
│   ├── core/
│   │   └── config.py
│   ├── models/            # Shared DB models (where scraped data gets saved)
│   ├── schemas/           # Shared Pydantic schemas
│   ├── scrapers/          # Extraction & parsing logic
│   │   ├── base.py
│   │   └── item_scraper.py
│   ├── tasks/             # Entrypoint functions for cron
│   │   └── run_scrapers.py
│   └── main.py
├── scripts/               # Optional: Wrapper scripts for cron execution
│   └── run_job.sh
├── .env
├── .gitignore
└── requirements.txt
```