-- ============================================
-- Multi-Armed Bandit API - Snowflake Schema
-- ============================================

-- Create database
CREATE DATABASE IF NOT EXISTS activeview_mab;

-- Create schema
CREATE SCHEMA IF NOT EXISTS activeview_mab.experiments;

-- Set context
USE DATABASE activeview_mab;
USE SCHEMA experiments;
