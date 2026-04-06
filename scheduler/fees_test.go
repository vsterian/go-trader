package main

import (
	"math"
	"testing"
)

func TestCalculateFuturesFee(t *testing.T) {
	cases := []struct {
		contracts      int
		feePerContract float64
		want           float64
	}{
		{1, 1.50, 1.50},
		{2, 1.50, 3.00},
		{10, 0.50, 5.00},
		{0, 1.50, 0.00},
		{5, 0, 0.00},
	}
	for _, tc := range cases {
		got := CalculateFuturesFee(tc.contracts, tc.feePerContract)
		if math.Abs(got-tc.want) > 0.001 {
			t.Errorf("CalculateFuturesFee(%d, %.2f) = %.2f, want %.2f", tc.contracts, tc.feePerContract, got, tc.want)
		}
	}
}

func TestCalculatePlatformFuturesFee(t *testing.T) {
	// With FuturesConfig
	sc := StrategyConfig{
		FuturesConfig: &FuturesConfig{FeePerContract: 1.50},
	}
	got := CalculatePlatformFuturesFee(sc, 3)
	if math.Abs(got-4.50) > 0.001 {
		t.Errorf("expected 4.50, got %.2f", got)
	}

	// Without FuturesConfig
	sc2 := StrategyConfig{}
	got2 := CalculatePlatformFuturesFee(sc2, 3)
	if got2 != 0 {
		t.Errorf("expected 0 with no FuturesConfig, got %.2f", got2)
	}
}

func TestCalculatePlatformSpotFee(t *testing.T) {
	cases := []struct {
		platform string
		value    float64
		wantZero bool
	}{
		{"alpaca", 10000.0, true},
		{"robinhood", 5000.0, true},
		{"hyperliquid", 1000.0, false},
		{"binanceus", 1000.0, false},
	}
	for _, tc := range cases {
		got := CalculatePlatformSpotFee(tc.platform, tc.value)
		if tc.wantZero && got != 0 {
			t.Errorf("CalculatePlatformSpotFee(%q, %.0f) = %.4f, want 0", tc.platform, tc.value, got)
		}
		if !tc.wantZero && got == 0 {
			t.Errorf("CalculatePlatformSpotFee(%q, %.0f) = 0, want > 0", tc.platform, tc.value)
		}
	}
}
