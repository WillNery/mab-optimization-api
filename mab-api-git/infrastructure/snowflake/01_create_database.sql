-- ============================================
-- Multi-Armed Bandit API
-- 01: Create Database and Schema
-- ============================================

-- Create database
CREATE DATABASE IF NOT EXISTS activeview_mab;

-- Use database
USE DATABASE activeview_mab;

-- Create schema
CREATE SCHEMA IF NOT EXISTS experiments;

-- Use schema
USE SCHEMA experiments;

-- Verify
SELECT CURRENT_DATABASE(), CURRENT_SCHEMA();
