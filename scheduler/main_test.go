package main

import (
	"os"
	"testing"
)

func TestIsLiveArgs(t *testing.T) {
	cases := []struct {
		name string
		args []string
		want bool
	}{
		{"live mode", []string{"sma", "BTC", "1h", "--mode=live"}, true},
		{"paper mode", []string{"sma", "BTC", "1h", "--mode=paper"}, false},
		{"no mode flag", []string{"sma", "BTC", "1h"}, false},
		{"empty args", []string{}, false},
		{"live at start", []string{"--mode=live", "sma"}, true},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := isLiveArgs(tc.args); got != tc.want {
				t.Errorf("isLiveArgs(%v) = %v, want %v", tc.args, got, tc.want)
			}
		})
	}
}

func TestHyperliquidIsLive(t *testing.T) {
	if hyperliquidIsLive([]string{"sma", "BTC", "1h", "--mode=live"}) != true {
		t.Error("expected true for --mode=live")
	}
	if hyperliquidIsLive([]string{"sma", "BTC", "1h"}) != false {
		t.Error("expected false without --mode=live")
	}
}

func TestHyperliquidSymbol(t *testing.T) {
	cases := []struct {
		args []string
		want string
	}{
		{[]string{"sma", "BTC", "1h"}, "BTC"},
		{[]string{"rsi", "ETH", "4h"}, "ETH"},
		{[]string{"sma"}, ""},
		{[]string{}, ""},
	}

	for _, tc := range cases {
		t.Run(tc.want, func(t *testing.T) {
			got := hyperliquidSymbol(tc.args)
			if got != tc.want {
				t.Errorf("hyperliquidSymbol(%v) = %q, want %q", tc.args, got, tc.want)
			}
		})
	}
}

func TestTopstepIsLive(t *testing.T) {
	if topstepIsLive([]string{"sma", "ES", "15m", "--mode=live"}) != true {
		t.Error("expected true for --mode=live")
	}
	if topstepIsLive([]string{"sma", "ES", "15m"}) != false {
		t.Error("expected false without --mode=live")
	}
}

func TestTopstepSymbol(t *testing.T) {
	cases := []struct {
		args []string
		want string
	}{
		{[]string{"sma", "ES", "15m"}, "ES"},
		{[]string{"rsi", "NQ", "5m"}, "NQ"},
		{[]string{"sma"}, ""},
		{[]string{}, ""},
	}

	for _, tc := range cases {
		t.Run(tc.want, func(t *testing.T) {
			got := topstepSymbol(tc.args)
			if got != tc.want {
				t.Errorf("topstepSymbol(%v) = %q, want %q", tc.args, got, tc.want)
			}
		})
	}
}

func TestRobinhoodIsLive(t *testing.T) {
	if robinhoodIsLive([]string{"sma", "BTC", "1h", "--mode=live"}) != true {
		t.Error("expected true for --mode=live")
	}
	if robinhoodIsLive([]string{"sma", "BTC", "1h"}) != false {
		t.Error("expected false without --mode=live")
	}
}

func TestRobinhoodSymbol(t *testing.T) {
	cases := []struct {
		args []string
		want string
	}{
		{[]string{"sma", "BTC", "1h"}, "BTC"},
		{[]string{"rsi"}, ""},
		{[]string{}, ""},
	}

	for _, tc := range cases {
		t.Run(tc.want, func(t *testing.T) {
			got := robinhoodSymbol(tc.args)
			if got != tc.want {
				t.Errorf("robinhoodSymbol(%v) = %q, want %q", tc.args, got, tc.want)
			}
		})
	}
}

func TestOKXIsLive(t *testing.T) {
	if okxIsLive([]string{"sma", "BTC", "1h", "--mode=live"}) != true {
		t.Error("expected true for --mode=live")
	}
	if okxIsLive([]string{"sma", "BTC", "1h"}) != false {
		t.Error("expected false without --mode=live")
	}
}

func TestOKXSymbol(t *testing.T) {
	cases := []struct {
		args []string
		want string
	}{
		{[]string{"sma", "BTC", "1h"}, "BTC"},
		{[]string{"rsi"}, ""},
		{[]string{}, ""},
	}

	for _, tc := range cases {
		t.Run(tc.want, func(t *testing.T) {
			got := okxSymbol(tc.args)
			if got != tc.want {
				t.Errorf("okxSymbol(%v) = %q, want %q", tc.args, got, tc.want)
			}
		})
	}
}

func TestOKXInstType(t *testing.T) {
	cases := []struct {
		name string
		args []string
		want string
	}{
		{"swap default", []string{"sma", "BTC", "1h"}, "swap"},
		{"explicit swap", []string{"sma", "BTC", "1h", "--inst-type=swap"}, "swap"},
		{"spot", []string{"sma", "BTC", "1h", "--inst-type=spot"}, "spot"},
		{"empty args", []string{}, "swap"},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := okxInstType(tc.args)
			if got != tc.want {
				t.Errorf("okxInstType(%v) = %q, want %q", tc.args, got, tc.want)
			}
		})
	}
}

func TestBinanceusIsLive(t *testing.T) {
if binanceusIsLive([]string{"sma", "BTC/USDC", "1h", "--mode=live"}) != true {
t.Error("expected true for --mode=live")
}
if binanceusIsLive([]string{"sma", "BTC/USDC", "1h"}) != false {
t.Error("expected false without --mode=live")
}
if binanceusIsLive([]string{"sma", "BTC/USDC", "1h", "--mode=paper"}) != false {
t.Error("expected false for --mode=paper")
}
}

func TestBinanceusSymbol(t *testing.T) {
cases := []struct {
args []string
want string
}{
{[]string{"sma", "BTC/USDC", "1h"}, "BTC/USDC"},
{[]string{"rsi"}, ""},
{[]string{}, ""},
{[]string{"momentum", "ETH/USDC", "1h", "--mode=live"}, "ETH/USDC"},
}

for _, tc := range cases {
t.Run(tc.want, func(t *testing.T) {
got := binanceusSymbol(tc.args)
if got != tc.want {
t.Errorf("binanceusSymbol(%v) = %q, want %q", tc.args, got, tc.want)
}
})
}
}

func TestExecuteBinanceUSResult(t *testing.T) {
s := &StrategyState{
InitialCapital: 1000,
Cash:           1000,
Positions:      map[string]*Position{},
}
sc := StrategyConfig{ID: "sma-btc", Platform: "binanceus", Type: "spot"}
result := &SpotResult{Signal: 1, Symbol: "BTC/USDC"}
execResult := &BinanceUSExecuteResult{
Execution: &BinanceUSExecution{
Action: "buy", Symbol: "BTC", Size: 0.015,
Fill: &BinanceUSFill{AvgPx: 67050, TotalSz: 0.015},
},
Platform: "binanceus",
}
logger := &StrategyLogger{stratID: "sma-btc", writer: os.Stdout}

trades, detail := executeBinanceUSResult(sc, s, result, execResult, "BUY", 67000, logger)
if trades != 1 {
t.Errorf("trades = %d, want 1", trades)
}
if detail == "" {
t.Error("expected non-empty detail")
}
if !contains(detail, "LIVE") {
t.Errorf("expected LIVE prefix in detail %q", detail)
}
if !contains(detail, "67050") {
t.Errorf("expected fill price in detail %q", detail)
}
}

func TestExecuteBinanceUSResultPaper(t *testing.T) {
s := &StrategyState{
InitialCapital: 1000,
Cash:           1000,
Positions:      map[string]*Position{},
}
sc := StrategyConfig{ID: "sma-btc", Platform: "binanceus", Type: "spot"}
result := &SpotResult{Signal: 1, Symbol: "BTC/USDC"}
logger := &StrategyLogger{stratID: "sma-btc", writer: os.Stdout}

// nil execResult = paper mode — should NOT have LIVE prefix
trades, detail := executeBinanceUSResult(sc, s, result, nil, "BUY", 67000, logger)
if trades != 1 {
t.Errorf("trades = %d, want 1", trades)
}
if contains(detail, "LIVE") {
t.Errorf("paper mode should NOT have LIVE prefix: %q", detail)
}
}

func contains(s, substr string) bool {
return len(s) >= len(substr) && (s == substr || len(s) > 0 && containsHelper(s, substr))
}

func containsHelper(s, substr string) bool {
for i := 0; i <= len(s)-len(substr); i++ {
if s[i:i+len(substr)] == substr {
return true
}
}
return false
}
