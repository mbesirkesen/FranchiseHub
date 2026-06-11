-- Marka yatırım aralığı kolonları (nullable). brand_service.apply_brand_filters
-- bu kolonları kullanıyordu ama model/şemada yoktu → bütçe filtreli aramalar 500
-- veriyordu. Null kalınca kod initial_cost'a fallback yapar.

ALTER TABLE brands ADD COLUMN IF NOT EXISTS min_investment_cost DOUBLE PRECISION;
ALTER TABLE brands ADD COLUMN IF NOT EXISTS max_investment_cost DOUBLE PRECISION;
