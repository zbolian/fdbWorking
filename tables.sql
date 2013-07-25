DROP TABLE fact_bookings;
DROP TABLE fact_incremental_bookings;
DROP TABLE fact_content;
DROP TABLE fact_revenue;
DROP TABLE fact_traffic;
DROP TABLE fact_payments;
DROP TABLE fact_current_client;
DROP TABLE fact_billing;
DROP TABLE fact_deal_count;

DROP TABLE dim_client;
DROP TABLE dim_date;
DROP TABLE dim_product;
DROP TABLE dim_contract_type;
DROP TABLE dim_content_type;
DROP TABLE dim_recurring;
DROP TABLE dim_invoice_type;
DROP TABLE dim_booking_type;
DROP TABLE dim_billing_freq;

CREATE TABLE dim_client(
	client_id VARCHAR(8) NOT NULL,   	/* Corresponds to Netsuite ID */
	name VARCHAR(255) NOT NULL,         /* Netsuite Name */
	afid VARCHAR(11) NOT NULL,			/* Account family ID */
	parent_id VARCHAR(8) NOT NULL,      /* Top-Level Netsuite Client ID */
	parent_name VARCHAR(255) NOT NULL,  /* Netsuite Name Top-Level OR Bundle Name */
	country VARCHAR(50) NULL,			/* Country of Billing Address */
	region VARCHAR(50) NULL,			/* Hierarchy based on Country */
	vertical VARCHAR(50) NULL,			/* Netsuite-based vertical (no Travel/Leisure) */
	first_booking DATE NULL,			/* Date of earliest booking for parent_name */
	cohort INTEGER NULL,				/* Fiscal year of the earliest booking for parent_name */
	goLiveCohort INTEGER NULL,			/* Fiscal year of the earliest revenue recognized for parent_name */
	oldNeverLive INTEGER NOT NULL,		/* 1 if a 1+ year old client and never had consistent recognized revenue, 0 otherwise */
	entity VARCHAR(2) NOT NULL, 		/* Two letter indication of which entity customer is affiliated with */
	ciq_id VARCHAR(50) NULL,			/* Capital IQ identifier mapped to the client id, 0 otherwise */
	bus_unit VARCHAR(50) NULL,			/* Business unit with which the client is associated */
	is_fortune500 INTEGER NOT NULL,		/* 0 or 1, indicating whether client_id is part of Fortune 500 or not*/
	is_ir500 INTEGER NOT NULL,			/* 0 or 1 indicating whether client_id is part of Internet Retailer 500 or not */
	ciq_ult_parent VARCHAR(255) NOT NULL,	/* Ultimate Parent Company from Capital IQ */
	customer_origination VARCHAR(50) NOT NULL, /*Defines original source of customer - acquisition or organic*/
	PRIMARY KEY (client_id)
);



CREATE TABLE dim_date(
	date_key INTEGER NOT NULL,		/* yyyymmdd in integer format */
	date_value DATE NOT NULL,		/* Date value */
	month_key INTEGER NOT NULL,		/* yyyymm in integer format */
	month_desc VARCHAR(10) NOT NULL,	/* yyyy-mm in text format */
	month_number SMALLINT NOT NULL,		/* 1-12 */
	year_number INTEGER NOT NULL,		/* Calendar year in integer format */
	fiscal_quarter_key INTEGER NOT NULL,	/* yyyyqq in integer format */
	fiscal_quarter_desc VARCHAR(10) NOT NULL, /* FYyyyyQq in text format */
	fiscal_year INTEGER NOT NULL,		/* Fiscal year in integer format */
	fiscal_quarter SMALLINT NOT NULL,	/* 1-4 */
	month_in_quarter SMALLINT NOT NULL,	/* 1-3 */
	PRIMARY KEY (date_key)
);



CREATE TABLE dim_product(
	product_id INTEGER NOT NULL,			/* Netsuite Product ID */
	name VARCHAR(255) NOT NULL,		/* Netsuite Name */
	family_name VARCHAR(255) NOT NULL,	/* Product Family Name from Mapping */
	PRIMARY KEY (product_id)
);



CREATE TABLE dim_billing_freq(
	bill_freq_id INTEGER NOT NULL,			/* Netsuite Billing Frequency ID */
	name VARCHAR(255) NOT NULL,		/* Netsuite Name */
	PRIMARY KEY (bill_freq_id)
);



CREATE TABLE dim_booking_type(
	booking_type_id INTEGER NOT NULL,			/* Numeric ID of booking type */
	name VARCHAR(255) NOT NULL,		/* Name */
	PRIMARY KEY (booking_type_id)
);


CREATE TABLE dim_invoice_type(
	invoice_type_id INTEGER NOT NULL,			/* Numeric ID of booking type */
	name VARCHAR(255) NOT NULL,		/* Name */
	PRIMARY KEY (invoice_type_id)
);


CREATE TABLE dim_contract_type(
	contract_type VARCHAR(50) NOT NULL,		/* New, Uptick, Downtick.  Applies to Incremental ASF */
	PRIMARY KEY (contract_type)
);


CREATE TABLE dim_content_type(
	content_type_id VARCHAR(1) NOT NULL,			/* R, Q, A, S.  Applies to Impressions and Page Views */
	PRIMARY KEY (content_type_id)
);


CREATE TABLE dim_recurring(
	recurring_id INTEGER NOT NULL,			/* 1 or 0.  Applies to revenue */
	PRIMARY KEY (recurring_id)
);


CREATE TABLE fact_bookings(
	client_id VARCHAR(8) NOT NULL,		/* Client Dimension */
	date_key INTEGER NOT NULL,		/* Date Dimension */
	product_id INTEGER NOT NULL,		/* Product Dimension */
	asf DECIMAL(12,2) NOT NULL		/* Cumulative ASF for Dimensions */
);

ALTER TABLE fact_bookings
ADD CONSTRAINT uc_fact_bookings1 UNIQUE (client_id, date_key, product_id);


CREATE TABLE fact_incremental_bookings(
	client_id VARCHAR(8) NOT NULL,		/* Client Dimension */
	date_key INTEGER NOT NULL,		
	product_id INTEGER NOT NULL,
	contract_type VARCHAR(50) NOT NULL,
	asf DECIMAL(12,2) NOT NULL,
	booking_type_id INTEGER NOT NULL
);

ALTER TABLE fact_incremental_bookings
ADD CONSTRAINT uc_fact_incremental_bookings1 UNIQUE (client_id, date_key, product_id, contract_type, booking_type_id);


CREATE TABLE fact_content(
	client_id VARCHAR(8) NOT NULL,
	date_key INTEGER NOT NULL,
	product_id INTEGER NOT NULL,
	volume INTEGER NOT NULL
);

ALTER TABLE fact_content
ADD CONSTRAINT uc_fact_content1 UNIQUE (client_id, date_key, product_id);


CREATE TABLE fact_traffic(
	client_id VARCHAR(8) NOT NULL,
	date_key INTEGER NOT NULL,
	product_id INTEGER NOT NULL,
	content_type_id VARCHAR(1) NOT NULL,
	page_views BIGINT NOT NULL,
	impressions BIGINT NOT NULL
);

ALTER TABLE fact_traffic
ADD CONSTRAINT uc_fact_traffic1 UNIQUE (client_id, date_key, product_id, content_type_id);


CREATE TABLE fact_revenue(
	client_id VARCHAR(8) NOT NULL,
	date_key INTEGER NOT NULL,
	product_id INTEGER NOT NULL,
	recurring_id INTEGER NOT NULL,
	revenue DECIMAL(12,2) NOT NULL
);

ALTER TABLE fact_revenue
ADD CONSTRAINT uc_fact_revenue1 UNIQUE (client_id, date_key, product_id, recurring_id);


CREATE TABLE fact_payments(
	client_id VARCHAR(8) NOT NULL,
	date_key INTEGER NOT NULL,
	payments DECIMAL(12,2) NOT NULL
);

ALTER TABLE fact_payments
ADD CONSTRAINT uc_fact_payments1 UNIQUE (client_id, date_key);

CREATE TABLE fact_billing(
	client_id VARCHAR(8) NOT NULL,
	date_key INTEGER NOT NULL,
	billing DECIMAL(12,2) NOT NULL,
	invoice_type_id INTEGER NOT NULL,
	bill_freq_id INTEGER NOT NULL
);

ALTER TABLE fact_billing
ADD CONSTRAINT uc_fact_billing1 UNIQUE (client_id, date_key, invoice_type_id, bill_freq_id);

CREATE TABLE fact_current_client (
	client_id VARCHAR(8) NOT NULL,
	date_key INTEGER NOT NULL,
	current_client INTEGER NOT NULL
);
ALTER TABLE fact_current_client
ADD CONSTRAINT uc_fact_current_client1 UNIQUE (client_id, date_key);

CREATE TABLE fact_deal_count(
	client_id VARCHAR(8) NOT NULL,
	date_key INTEGER NOT NULL,
	deal_count INTEGER NOT NULL
);

ALTER TABLE fact_deal_count
ADD CONSTRAINT uc_fact_deal_count1 UNIQUE (client_id, date_key);


CREATE INDEX id_index_content_date ON fact_content(date_key);
CREATE INDEX id_index_content_client ON fact_content(client_id);
CREATE INDEX id_index_content_product ON fact_content(product_id);

CREATE INDEX id_index_bookings_date ON fact_bookings(date_key);
CREATE INDEX id_index_bookings_client ON fact_bookings(client_id);
CREATE INDEX id_index_bookings_product ON fact_bookings(product_id);

CREATE INDEX id_index_bookings_date ON fact_incremental_bookings(date_key);
CREATE INDEX id_index_bookings_client ON fact_incremental_bookings(client_id);
CREATE INDEX id_index_bookings_product ON fact_incremental_bookings(product_id);
CREATE INDEX id_index_bookings_contractType ON fact_incremental_bookings(contract_type);

CREATE INDEX id_index_revenue_date ON fact_revenue(date_key);
CREATE INDEX id_index_revenue_client ON fact_revenue(client_id);
CREATE INDEX id_index_revenue_product ON fact_revenue(product_id);
CREATE INDEX id_index_revenue_recurring ON fact_revenue(recurring_id);

CREATE INDEX id_index_traffic_date ON fact_traffic(date_key);
CREATE INDEX id_index_traffic_client ON fact_traffic(client_id);
CREATE INDEX id_index_traffic_product ON fact_traffic(product_id);
CREATE INDEX id_index_traffic_contentType ON fact_traffic(content_type_id);

CREATE INDEX id_index_payments_date ON fact_payments(date_key);
CREATE INDEX id_index_payments_client ON fact_payments(client_id);

CREATE INDEX id_index_netbilling_date ON fact_billing(date_key);
CREATE INDEX id_index_netbilling_client ON fact_billing(client_id);

CREATE INDEX id_index_current_client_date ON fact_current_client(date_key);
CREATE INDEX id_index_current_client_client ON fact_current_client(client_id);

CREATE INDEX id_index_deal_count_date ON fact_deal_count(date_key);
CREATE INDEX id_index_deal_count_client ON fact_deal_count(client_id);

