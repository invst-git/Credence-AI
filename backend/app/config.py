from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    anthropic_api_key: str
    landingai_api_key: str = ""  # LandingAI DPT-2 for document OCR
    database_url: str = ""  # Supabase PostgreSQL for citizen verification
    supabase_url: str = ""  # Supabase project URL for Auth
    supabase_anon_key: str = ""  # Supabase anon key for Auth

    # LLM model - reads from ANTHROPIC_MODEL env var
    anthropic_model: str = "claude-3-7-sonnet-20250219"
    
    @property
    def model_name(self) -> str:
        return self.anthropic_model

    # Hard rules
    min_age: int = 21
    max_age: int = 58

    min_salaried_income: int = 15000                # per month
    min_self_employed_income_annual: int = 180000   # per year

    min_total_exp_months: int = 12                  # 1 year total
    min_current_job_months: int = 6                 # 6 months in current job
    min_business_vintage_months: int = 12           # 1 year business

    max_loan_amount: int = 3_500_000                # Rs 35L

    annual_interest_rate: float = 0.16              # 16% nominal for EMI estimate
    max_foir: float = 0.65                          # 65%

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",      # ignore extra env vars like ANTHROPIC_MODEL
    )


settings = Settings()
