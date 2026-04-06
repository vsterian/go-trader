package main

import (
	"encoding/json"
	"testing"
)

// These tests verify JSON deserialization of executor result structs, not subprocess
// execution behavior (timeouts, concurrency limits, etc.).

func TestSpotResultJSON(t *testing.T) {
	raw := `{
		"strategy": "sma_crossover",
		"symbol": "BTC/USDC",
		"timeframe": "1h",
		"signal": 1,
		"price": 60000.5,
		"indicators": {"sma_fast": 59000, "sma_slow": 58000},
		"timestamp": "2026-01-01T00:00:00Z"
	}`

	var result SpotResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatalf("unmarshal failed: %v", err)
	}

	if result.Strategy != "sma_crossover" {
		t.Errorf("Strategy = %q, want %q", result.Strategy, "sma_crossover")
	}
	if result.Signal != 1 {
		t.Errorf("Signal = %d, want 1", result.Signal)
	}
	if result.Price != 60000.5 {
		t.Errorf("Price = %g, want 60000.5", result.Price)
	}
	if result.Error != "" {
		t.Errorf("Error should be empty, got %q", result.Error)
	}
}

func TestSpotResultErrorJSON(t *testing.T) {
	raw := `{"strategy": "sma", "error": "API timeout"}`
	var result SpotResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatal(err)
	}
	if result.Error != "API timeout" {
		t.Errorf("Error = %q, want %q", result.Error, "API timeout")
	}
}

func TestHyperliquidResultJSON(t *testing.T) {
	raw := `{
		"strategy": "sma",
		"symbol": "BTC",
		"timeframe": "1h",
		"signal": -1,
		"price": 55000,
		"mode": "paper",
		"platform": "hyperliquid",
		"timestamp": "2026-01-01T00:00:00Z"
	}`

	var result HyperliquidResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatal(err)
	}
	if result.Signal != -1 {
		t.Errorf("Signal = %d, want -1", result.Signal)
	}
	if result.Mode != "paper" {
		t.Errorf("Mode = %q, want %q", result.Mode, "paper")
	}
	if result.Platform != "hyperliquid" {
		t.Errorf("Platform = %q, want %q", result.Platform, "hyperliquid")
	}
}

func TestHyperliquidExecuteResultJSON(t *testing.T) {
	raw := `{
		"execution": {
			"action": "buy",
			"symbol": "BTC",
			"size": 0.01,
			"fill": {"avg_px": 55000.5, "total_sz": 0.01}
		},
		"platform": "hyperliquid",
		"timestamp": "2026-01-01T00:00:00Z"
	}`

	var result HyperliquidExecuteResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatal(err)
	}
	if result.Execution == nil {
		t.Fatal("Execution should not be nil")
	}
	if result.Execution.Action != "buy" {
		t.Errorf("Action = %q, want %q", result.Execution.Action, "buy")
	}
	if result.Execution.Fill == nil {
		t.Fatal("Fill should not be nil")
	}
	if result.Execution.Fill.AvgPx != 55000.5 {
		t.Errorf("AvgPx = %g, want 55000.5", result.Execution.Fill.AvgPx)
	}
}

func TestTopStepResultJSON(t *testing.T) {
	raw := `{
		"strategy": "sma",
		"symbol": "ES",
		"timeframe": "15m",
		"signal": 1,
		"price": 5200.5,
		"contract_spec": {"tick_size": 0.25, "tick_value": 12.5, "multiplier": 50, "margin": 500},
		"market_open": true,
		"mode": "paper",
		"platform": "topstep"
	}`

	var result TopStepResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatal(err)
	}
	if result.ContractSpec.Multiplier != 50 {
		t.Errorf("Multiplier = %g, want 50", result.ContractSpec.Multiplier)
	}
	if !result.MarketOpen {
		t.Error("MarketOpen should be true")
	}
	if result.ContractSpec.Margin != 500 {
		t.Errorf("Margin = %g, want 500", result.ContractSpec.Margin)
	}
}

func TestTopStepExecuteResultJSON(t *testing.T) {
	raw := `{
		"execution": {
			"action": "buy",
			"symbol": "ES",
			"contracts": 2,
			"fill": {"avg_px": 5200.25, "total_contracts": 2}
		},
		"platform": "topstep"
	}`

	var result TopStepExecuteResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatal(err)
	}
	if result.Execution.Contracts != 2 {
		t.Errorf("Contracts = %d, want 2", result.Execution.Contracts)
	}
	if result.Execution.Fill.TotalContracts != 2 {
		t.Errorf("TotalContracts = %d, want 2", result.Execution.Fill.TotalContracts)
	}
}

func TestRobinhoodResultJSON(t *testing.T) {
	raw := `{
		"strategy": "sma",
		"symbol": "BTC",
		"signal": 1,
		"price": 60000,
		"mode": "paper",
		"platform": "robinhood"
	}`

	var result RobinhoodResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatal(err)
	}
	if result.Platform != "robinhood" {
		t.Errorf("Platform = %q, want %q", result.Platform, "robinhood")
	}
}

func TestRobinhoodExecuteResultJSON(t *testing.T) {
	raw := `{
		"execution": {
			"action": "buy",
			"symbol": "BTC",
			"amount_usd": 500,
			"fill": {"avg_px": 60000.5, "quantity": 0.00833}
		},
		"platform": "robinhood"
	}`

	var result RobinhoodExecuteResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatal(err)
	}
	if result.Execution.AmountUSD != 500 {
		t.Errorf("AmountUSD = %g, want 500", result.Execution.AmountUSD)
	}
}

func TestOKXResultJSON(t *testing.T) {
	raw := `{
		"strategy": "sma",
		"symbol": "BTC",
		"signal": -1,
		"price": 55000,
		"mode": "live",
		"platform": "okx"
	}`

	var result OKXResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatal(err)
	}
	if result.Signal != -1 {
		t.Errorf("Signal = %d, want -1", result.Signal)
	}
	if result.Platform != "okx" {
		t.Errorf("Platform = %q, want %q", result.Platform, "okx")
	}
}

func TestOKXExecuteResultJSON(t *testing.T) {
	raw := `{
		"execution": {
			"action": "sell",
			"symbol": "BTC",
			"size": 0.05,
			"fill": {"avg_px": 55000, "total_sz": 0.05}
		},
		"platform": "okx"
	}`

	var result OKXExecuteResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatal(err)
	}
	if result.Execution.Size != 0.05 {
		t.Errorf("Size = %g, want 0.05", result.Execution.Size)
	}
}

func TestContractSpecJSON(t *testing.T) {
	raw := `{"tick_size": 0.25, "tick_value": 12.5, "multiplier": 50, "margin": 6600}`
	var spec ContractSpec
	if err := json.Unmarshal([]byte(raw), &spec); err != nil {
		t.Fatal(err)
	}
	if spec.TickSize != 0.25 {
		t.Errorf("TickSize = %g, want 0.25", spec.TickSize)
	}
	if spec.TickValue != 12.5 {
		t.Errorf("TickValue = %g, want 12.5", spec.TickValue)
	}
	if spec.Multiplier != 50 {
		t.Errorf("Multiplier = %g, want 50", spec.Multiplier)
	}
	if spec.Margin != 6600 {
		t.Errorf("Margin = %g, want 6600", spec.Margin)
	}
}

func TestBinanceUSExecuteResultJSON(t *testing.T) {
	raw := `{
		"execution": {
			"action": "buy",
			"symbol": "BTC",
			"size": 0.001,
			"fill": {"avg_px": 67050, "total_sz": 0.001}
		},
		"platform": "binanceus",
		"timestamp": "2025-01-01T00:00:00Z"
	}`

	var result BinanceUSExecuteResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatal(err)
	}
	if result.Execution == nil {
		t.Fatal("Execution is nil")
	}
	if result.Execution.Action != "buy" {
		t.Errorf("Action = %q, want buy", result.Execution.Action)
	}
	if result.Execution.Size != 0.001 {
		t.Errorf("Size = %g, want 0.001", result.Execution.Size)
	}
	if result.Execution.Fill == nil {
		t.Fatal("Fill is nil")
	}
	if result.Execution.Fill.AvgPx != 67050 {
		t.Errorf("AvgPx = %g, want 67050", result.Execution.Fill.AvgPx)
	}
	if result.Execution.Fill.TotalSz != 0.001 {
		t.Errorf("TotalSz = %g, want 0.001", result.Execution.Fill.TotalSz)
	}
	if result.Platform != "binanceus" {
		t.Errorf("Platform = %q, want binanceus", result.Platform)
	}
}

func TestBinanceUSExecuteResultErrorJSON(t *testing.T) {
	raw := `{
		"execution": null,
		"platform": "binanceus",
		"timestamp": "2025-01-01T00:00:00Z",
		"error": "order value $5.00 below min notional $10.00"
	}`

	var result BinanceUSExecuteResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatal(err)
	}
	if result.Execution != nil {
		t.Error("Execution should be nil on error")
	}
	if result.Error != "order value $5.00 below min notional $10.00" {
		t.Errorf("Error = %q, want min notional error", result.Error)
	}
}

func TestBinanceUSExecuteResultSellJSON(t *testing.T) {
	raw := `{
		"execution": {
			"action": "sell",
			"symbol": "ETH",
			"size": 0.5,
			"fill": {"avg_px": 3400.5, "total_sz": 0.5}
		},
		"platform": "binanceus"
	}`

	var result BinanceUSExecuteResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatal(err)
	}
	if result.Execution.Action != "sell" {
		t.Errorf("Action = %q, want sell", result.Execution.Action)
	}
	if result.Execution.Fill.AvgPx != 3400.5 {
		t.Errorf("AvgPx = %g, want 3400.5", result.Execution.Fill.AvgPx)
	}
}

func TestAlpacaExecuteResultJSON(t *testing.T) {
	raw := `{
		"execution": {
			"action": "buy",
			"symbol": "AAPL",
			"amount_usd": 1000,
			"fill": {"avg_px": 195.50, "total_sz": 5.0}
		},
		"platform": "alpaca",
		"timestamp": "2025-01-01T00:00:00Z"
	}`

	var result AlpacaExecuteResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatal(err)
	}
	if result.Execution == nil {
		t.Fatal("Execution is nil")
	}
	if result.Execution.Action != "buy" {
		t.Errorf("Action = %q, want buy", result.Execution.Action)
	}
	if result.Execution.AmountUSD != 1000 {
		t.Errorf("AmountUSD = %g, want 1000", result.Execution.AmountUSD)
	}
	if result.Execution.Fill == nil {
		t.Fatal("Fill is nil")
	}
	if result.Execution.Fill.AvgPx != 195.50 {
		t.Errorf("AvgPx = %g, want 195.50", result.Execution.Fill.AvgPx)
	}
	if result.Execution.Fill.TotalSz != 5.0 {
		t.Errorf("TotalSz = %g, want 5.0", result.Execution.Fill.TotalSz)
	}
	if result.Platform != "alpaca" {
		t.Errorf("Platform = %q, want alpaca", result.Platform)
	}
}

func TestAlpacaExecuteResultErrorJSON(t *testing.T) {
	raw := `{
		"execution": null,
		"platform": "alpaca",
		"timestamp": "2025-01-01T00:00:00Z",
		"error": "need at least 1 share ($195.50), insufficient funds"
	}`

	var result AlpacaExecuteResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatal(err)
	}
	if result.Execution != nil {
		t.Error("Execution should be nil on error")
	}
	if result.Error == "" {
		t.Error("Error should not be empty")
	}
}

func TestAlpacaExecuteResultSellJSON(t *testing.T) {
	raw := `{
		"execution": {
			"action": "sell",
			"symbol": "SPY",
			"quantity": 10.0,
			"fill": {"avg_px": 580.25, "total_sz": 10.0}
		},
		"platform": "alpaca"
	}`

	var result AlpacaExecuteResult
	if err := json.Unmarshal([]byte(raw), &result); err != nil {
		t.Fatal(err)
	}
	if result.Execution.Action != "sell" {
		t.Errorf("Action = %q, want sell", result.Execution.Action)
	}
	if result.Execution.Quantity != 10.0 {
		t.Errorf("Quantity = %g, want 10.0", result.Execution.Quantity)
	}
	if result.Execution.Fill.AvgPx != 580.25 {
		t.Errorf("AvgPx = %g, want 580.25", result.Execution.Fill.AvgPx)
	}
}
