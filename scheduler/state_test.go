package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestNewAppState(t *testing.T) {
	state := NewAppState()
	if state.CycleCount != 0 {
		t.Errorf("CycleCount = %d, want 0", state.CycleCount)
	}
	if state.Strategies == nil {
		t.Error("Strategies map should not be nil")
	}
	if len(state.Strategies) != 0 {
		t.Errorf("Strategies should be empty, got %d", len(state.Strategies))
	}
}

func TestNewStrategyState(t *testing.T) {
	cfg := StrategyConfig{
		ID:             "test-spot-btc",
		Type:           "spot",
		Platform:       "binanceus",
		Capital:        1000,
		MaxDrawdownPct: 60,
	}
	s := NewStrategyState(cfg)
	if s.ID != "test-spot-btc" {
		t.Errorf("ID = %q, want %q", s.ID, "test-spot-btc")
	}
	if s.Type != "spot" {
		t.Errorf("Type = %q, want %q", s.Type, "spot")
	}
	if s.Platform != "binanceus" {
		t.Errorf("Platform = %q, want %q", s.Platform, "binanceus")
	}
	if s.Cash != 1000 {
		t.Errorf("Cash = %g, want 1000", s.Cash)
	}
	if s.InitialCapital != 1000 {
		t.Errorf("InitialCapital = %g, want 1000", s.InitialCapital)
	}
	if s.Positions == nil {
		t.Error("Positions should not be nil")
	}
	if s.OptionPositions == nil {
		t.Error("OptionPositions should not be nil")
	}
	if s.TradeHistory == nil {
		t.Error("TradeHistory should not be nil")
	}
	if s.RiskState.PeakValue != 1000 {
		t.Errorf("RiskState.PeakValue = %g, want 1000", s.RiskState.PeakValue)
	}
	if s.RiskState.MaxDrawdownPct != 60 {
		t.Errorf("RiskState.MaxDrawdownPct = %g, want 60", s.RiskState.MaxDrawdownPct)
	}
}

func TestLoadStateMissingFile(t *testing.T) {
	state, err := LoadState(filepath.Join(t.TempDir(), "nonexistent.json"))
	if err != nil {
		t.Fatalf("LoadState should not error for missing file: %v", err)
	}
	if state.CycleCount != 0 {
		t.Errorf("CycleCount = %d, want 0", state.CycleCount)
	}
	if state.Strategies == nil {
		t.Error("Strategies should be initialized")
	}
}

func TestSaveAndLoadStateRoundTrip(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "state.json")

	state := NewAppState()
	state.CycleCount = 42
	state.LastCycle = time.Date(2026, 1, 1, 12, 0, 0, 0, time.UTC)
	state.Strategies["test-btc"] = &StrategyState{
		ID:             "test-btc",
		Type:           "spot",
		Platform:       "binanceus",
		Cash:           950.5,
		InitialCapital: 1000,
		Positions: map[string]*Position{
			"BTC/USDC": {Symbol: "BTC/USDC", Quantity: 0.01, AvgCost: 50000, Side: "long"},
		},
		OptionPositions: make(map[string]*OptionPosition),
		TradeHistory:    []Trade{{StrategyID: "test-btc", Symbol: "BTC/USDC", Side: "buy"}},
	}

	if err := SaveState(path, state); err != nil {
		t.Fatalf("SaveState failed: %v", err)
	}

	loaded, err := LoadState(path)
	if err != nil {
		t.Fatalf("LoadState failed: %v", err)
	}

	if loaded.CycleCount != 42 {
		t.Errorf("CycleCount = %d, want 42", loaded.CycleCount)
	}
	s := loaded.Strategies["test-btc"]
	if s == nil {
		t.Fatal("Strategy 'test-btc' not found")
	}
	if s.Cash != 950.5 {
		t.Errorf("Cash = %g, want 950.5", s.Cash)
	}
	pos := s.Positions["BTC/USDC"]
	if pos == nil {
		t.Fatal("Position BTC/USDC not found")
	}
	if pos.Quantity != 0.01 {
		t.Errorf("Quantity = %g, want 0.01", pos.Quantity)
	}
}

func TestLoadStateNilMapsFixed(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "state.json")

	// Write state with nil maps (simulated by omitting fields)
	raw := `{"cycle_count": 1, "strategies": {"s1": {"id": "s1"}}}`
	if err := os.WriteFile(path, []byte(raw), 0600); err != nil {
		t.Fatal(err)
	}

	state, err := LoadState(path)
	if err != nil {
		t.Fatalf("LoadState failed: %v", err)
	}

	s := state.Strategies["s1"]
	if s.Positions == nil {
		t.Error("Positions should be initialized, not nil")
	}
	if s.OptionPositions == nil {
		t.Error("OptionPositions should be initialized, not nil")
	}
	if s.TradeHistory == nil {
		t.Error("TradeHistory should be initialized, not nil")
	}
}

func TestLoadStateInvalidJSON(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "state.json")
	if err := os.WriteFile(path, []byte("not json"), 0600); err != nil {
		t.Fatal(err)
	}

	_, err := LoadState(path)
	if err == nil {
		t.Error("expected error for invalid JSON")
	}
}

func TestSaveStateTrimsTradeHistory(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "state.json")

	state := NewAppState()
	s := &StrategyState{
		ID:              "test",
		Positions:       make(map[string]*Position),
		OptionPositions: make(map[string]*OptionPosition),
	}
	// Add more than maxTradeHistory trades
	for i := 0; i < maxTradeHistory+100; i++ {
		s.TradeHistory = append(s.TradeHistory, Trade{StrategyID: "test", Symbol: "BTC"})
	}
	state.Strategies["test"] = s

	if err := SaveState(path, state); err != nil {
		t.Fatalf("SaveState failed: %v", err)
	}

	loaded, err := LoadState(path)
	if err != nil {
		t.Fatalf("LoadState failed: %v", err)
	}

	if len(loaded.Strategies["test"].TradeHistory) != maxTradeHistory {
		t.Errorf("TradeHistory len = %d, want %d", len(loaded.Strategies["test"].TradeHistory), maxTradeHistory)
	}
}

func TestSaveStateAtomicWrite(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "state.json")

	state := NewAppState()
	state.CycleCount = 10

	if err := SaveState(path, state); err != nil {
		t.Fatal(err)
	}

	// tmp file should not remain
	if _, err := os.Stat(path + ".tmp"); !os.IsNotExist(err) {
		t.Error("temp file should not exist after save")
	}

	// Actual file should exist and be valid
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var loaded AppState
	if err := json.Unmarshal(data, &loaded); err != nil {
		t.Fatalf("saved file is not valid JSON: %v", err)
	}
	if loaded.CycleCount != 10 {
		t.Errorf("CycleCount = %d, want 10", loaded.CycleCount)
	}
}

func TestSaveStateCreatesDirectories(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "sub", "dir", "state.json")

	state := NewAppState()
	if err := SaveState(path, state); err != nil {
		t.Fatalf("SaveState should create directories: %v", err)
	}
	if _, err := os.Stat(path); err != nil {
		t.Error("state file should exist")
	}
}

func TestValidateState(t *testing.T) {
	state := NewAppState()
	state.Strategies["s1"] = &StrategyState{
		ID:             "s1",
		InitialCapital: -100, // invalid
		Cash:           -50,  // negative
		Positions: map[string]*Position{
			"BTC/USDC": {Quantity: 0.01, Side: "long"},
			"ETH/USDC": {Quantity: 0, Side: "long"},   // invalid: zero
			"SOL/USDC": {Quantity: -1, Side: "short"}, // invalid: negative
		},
		OptionPositions: map[string]*OptionPosition{
			"valid":   {Action: "buy", OptionType: "call", Quantity: 1},
			"badact":  {Action: "invalid", OptionType: "call", Quantity: 1},
			"badtype": {Action: "sell", OptionType: "invalid", Quantity: 1},
			"badqty":  {Action: "buy", OptionType: "put", Quantity: 0},
		},
		TradeHistory: []Trade{},
	}

	ValidateState(state)

	s := state.Strategies["s1"]
	if s.InitialCapital != 0 {
		t.Errorf("InitialCapital should be reset to 0, got %g", s.InitialCapital)
	}
	if s.Cash != 0 {
		t.Errorf("Cash should be clamped to 0, got %g", s.Cash)
	}
	if _, ok := s.Positions["BTC/USDC"]; !ok {
		t.Error("valid position BTC/USDC should remain")
	}
	if _, ok := s.Positions["ETH/USDC"]; ok {
		t.Error("zero-quantity position should be removed")
	}
	if _, ok := s.Positions["SOL/USDC"]; ok {
		t.Error("negative-quantity position should be removed")
	}
	if _, ok := s.OptionPositions["valid"]; !ok {
		t.Error("valid option should remain")
	}
	if _, ok := s.OptionPositions["badact"]; ok {
		t.Error("invalid-action option should be removed")
	}
	if _, ok := s.OptionPositions["badtype"]; ok {
		t.Error("invalid-type option should be removed")
	}
	if _, ok := s.OptionPositions["badqty"]; ok {
		t.Error("zero-quantity option should be removed")
	}
}

func TestLoadPlatformStatesNoPlatforms(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "state.json")

	state := NewAppState()
	state.CycleCount = 5
	SaveState(path, state)

	cfg := &Config{StateFile: path, Platforms: map[string]*PlatformConfig{}}
	loaded, err := LoadPlatformStates(cfg)
	if err != nil {
		t.Fatalf("LoadPlatformStates failed: %v", err)
	}
	if loaded.CycleCount != 5 {
		t.Errorf("CycleCount = %d, want 5", loaded.CycleCount)
	}
}

func TestLoadPlatformStatesMerge(t *testing.T) {
	dir := t.TempDir()

	// Create two platform state files
	hlDir := filepath.Join(dir, "platforms", "hyperliquid")
	os.MkdirAll(hlDir, 0755)
	hlState := NewAppState()
	hlState.CycleCount = 10
	hlState.Strategies["hl-btc"] = &StrategyState{
		ID:              "hl-btc",
		Platform:        "hyperliquid",
		Cash:            500,
		Positions:       make(map[string]*Position),
		OptionPositions: make(map[string]*OptionPosition),
		TradeHistory:    []Trade{},
	}
	SaveState(filepath.Join(hlDir, "state.json"), hlState)

	binDir := filepath.Join(dir, "platforms", "binanceus")
	os.MkdirAll(binDir, 0755)
	binState := NewAppState()
	binState.CycleCount = 8
	binState.Strategies["spot-eth"] = &StrategyState{
		ID:              "spot-eth",
		Platform:        "binanceus",
		Cash:            300,
		Positions:       make(map[string]*Position),
		OptionPositions: make(map[string]*OptionPosition),
		TradeHistory:    []Trade{},
	}
	SaveState(filepath.Join(binDir, "state.json"), binState)

	cfg := &Config{
		Platforms: map[string]*PlatformConfig{
			"hyperliquid": {StateFile: filepath.Join(hlDir, "state.json")},
			"binanceus":   {StateFile: filepath.Join(binDir, "state.json")},
		},
	}

	merged, err := LoadPlatformStates(cfg)
	if err != nil {
		t.Fatalf("LoadPlatformStates failed: %v", err)
	}
	if merged.CycleCount != 10 {
		t.Errorf("CycleCount = %d, want 10 (max)", merged.CycleCount)
	}
	if _, ok := merged.Strategies["hl-btc"]; !ok {
		t.Error("hl-btc should be in merged state")
	}
	if _, ok := merged.Strategies["spot-eth"]; !ok {
		t.Error("spot-eth should be in merged state")
	}
}

func TestSavePlatformStates(t *testing.T) {
	dir := t.TempDir()

	hlDir := filepath.Join(dir, "platforms", "hyperliquid")
	binDir := filepath.Join(dir, "platforms", "binanceus")

	cfg := &Config{
		Platforms: map[string]*PlatformConfig{
			"hyperliquid": {StateFile: filepath.Join(hlDir, "state.json")},
			"binanceus":   {StateFile: filepath.Join(binDir, "state.json")},
		},
	}

	state := NewAppState()
	state.CycleCount = 15
	state.Strategies["hl-btc"] = &StrategyState{
		ID:              "hl-btc",
		Platform:        "hyperliquid",
		Cash:            500,
		Positions:       make(map[string]*Position),
		OptionPositions: make(map[string]*OptionPosition),
		TradeHistory:    []Trade{},
	}
	state.Strategies["spot-eth"] = &StrategyState{
		ID:              "spot-eth",
		Platform:        "binanceus",
		Cash:            300,
		Positions:       make(map[string]*Position),
		OptionPositions: make(map[string]*OptionPosition),
		TradeHistory:    []Trade{},
	}

	if err := SavePlatformStates(state, cfg); err != nil {
		t.Fatalf("SavePlatformStates failed: %v", err)
	}

	// Verify hyperliquid state file
	hlLoaded, err := LoadState(filepath.Join(hlDir, "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := hlLoaded.Strategies["hl-btc"]; !ok {
		t.Error("hl-btc should be in hyperliquid state file")
	}
	if _, ok := hlLoaded.Strategies["spot-eth"]; ok {
		t.Error("spot-eth should not be in hyperliquid state file")
	}

	// Verify binanceus state file
	binLoaded, err := LoadState(filepath.Join(binDir, "state.json"))
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := binLoaded.Strategies["spot-eth"]; !ok {
		t.Error("spot-eth should be in binanceus state file")
	}
}

func TestSavePlatformStatesNoPlatforms(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "state.json")

	cfg := &Config{StateFile: path, Platforms: map[string]*PlatformConfig{}}
	state := NewAppState()
	state.CycleCount = 7

	if err := SavePlatformStates(state, cfg); err != nil {
		t.Fatal(err)
	}

	loaded, err := LoadState(path)
	if err != nil {
		t.Fatal(err)
	}
	if loaded.CycleCount != 7 {
		t.Errorf("CycleCount = %d, want 7", loaded.CycleCount)
	}
}

// TestLoadPlatformStatesFallback verifies that strategies whose platform is not in the
// platforms map are still loaded from the fallback state file (cfg.StateFile).
// This prevents state loss when a new platform is added without listing existing platforms.
func TestLoadPlatformStatesFallback(t *testing.T) {
dir := t.TempDir()

// Create a fallback state file with binanceus strategies (simulating old state.json).
fallbackPath := filepath.Join(dir, "state.json")
oldState := NewAppState()
oldState.CycleCount = 50
oldState.Strategies["rsi-eth"] = &StrategyState{
ID:       "rsi-eth",
Platform: "binanceus",
Cash:     4.91,
Positions: map[string]*Position{
"ETH/USDC": {Symbol: "ETH/USDC", Quantity: 0.046044, AvgCost: 2063.23, Side: "long"},
},
OptionPositions: make(map[string]*OptionPosition),
TradeHistory:    []Trade{{StrategyID: "rsi-eth", Side: "buy", Quantity: 0.046044}},
}
SaveState(fallbackPath, oldState)

// Create an alpaca state file.
alpacaDir := filepath.Join(dir, "platforms", "alpaca")
os.MkdirAll(alpacaDir, 0755)
alpacaState := NewAppState()
alpacaState.CycleCount = 5
alpacaState.Strategies["alpaca-sma-spy"] = &StrategyState{
ID: "alpaca-sma-spy", Platform: "alpaca", Cash: 1000,
Positions: make(map[string]*Position), OptionPositions: make(map[string]*OptionPosition),
TradeHistory: []Trade{},
}
SaveState(filepath.Join(alpacaDir, "state.json"), alpacaState)

// Config only has alpaca — binanceus NOT listed (this is the bug scenario).
cfg := &Config{
StateFile: fallbackPath,
Platforms: map[string]*PlatformConfig{
"alpaca": {StateFile: filepath.Join(alpacaDir, "state.json")},
},
}

merged, err := LoadPlatformStates(cfg)
if err != nil {
t.Fatalf("LoadPlatformStates failed: %v", err)
}

// Both strategies should be present.
if _, ok := merged.Strategies["rsi-eth"]; !ok {
t.Error("rsi-eth should be loaded from fallback state file")
}
if _, ok := merged.Strategies["alpaca-sma-spy"]; !ok {
t.Error("alpaca-sma-spy should be loaded from platform state file")
}

// Verify the position was preserved.
rsi := merged.Strategies["rsi-eth"]
if pos, ok := rsi.Positions["ETH/USDC"]; !ok {
t.Error("ETH/USDC position should be preserved")
} else if pos.Quantity != 0.046044 {
t.Errorf("ETH position quantity = %f, want 0.046044", pos.Quantity)
}
if rsi.Cash != 4.91 {
t.Errorf("rsi-eth cash = %f, want 4.91", rsi.Cash)
}

// Cycle count should be max(50, 5) = 50.
if merged.CycleCount != 50 {
t.Errorf("CycleCount = %d, want 50", merged.CycleCount)
}
}

// TestSavePlatformStatesFallback verifies that strategies whose platform is not in the
// platforms map are saved to the fallback state file instead of being silently dropped.
func TestSavePlatformStatesFallback(t *testing.T) {
dir := t.TempDir()
fallbackPath := filepath.Join(dir, "state.json")

alpacaDir := filepath.Join(dir, "platforms", "alpaca")

cfg := &Config{
StateFile: fallbackPath,
Platforms: map[string]*PlatformConfig{
"alpaca": {StateFile: filepath.Join(alpacaDir, "state.json")},
},
}

state := NewAppState()
state.CycleCount = 20
state.Strategies["rsi-eth"] = &StrategyState{
ID: "rsi-eth", Platform: "binanceus", Cash: 4.91,
Positions: map[string]*Position{
"ETH/USDC": {Symbol: "ETH/USDC", Quantity: 0.046044, AvgCost: 2063.23, Side: "long"},
},
OptionPositions: make(map[string]*OptionPosition),
TradeHistory:    []Trade{},
}
state.Strategies["alpaca-sma-spy"] = &StrategyState{
ID: "alpaca-sma-spy", Platform: "alpaca", Cash: 1000,
Positions: make(map[string]*Position), OptionPositions: make(map[string]*OptionPosition),
TradeHistory: []Trade{},
}

if err := SavePlatformStates(state, cfg); err != nil {
t.Fatalf("SavePlatformStates failed: %v", err)
}

// Verify alpaca state file has only alpaca strategies.
alpacaLoaded, err := LoadState(filepath.Join(alpacaDir, "state.json"))
if err != nil {
t.Fatal(err)
}
if _, ok := alpacaLoaded.Strategies["alpaca-sma-spy"]; !ok {
t.Error("alpaca-sma-spy should be in alpaca state file")
}
if _, ok := alpacaLoaded.Strategies["rsi-eth"]; ok {
t.Error("rsi-eth should NOT be in alpaca state file")
}

// Verify fallback state file has binanceus strategies.
fallbackLoaded, err := LoadState(fallbackPath)
if err != nil {
t.Fatal(err)
}
if _, ok := fallbackLoaded.Strategies["rsi-eth"]; !ok {
t.Error("rsi-eth should be saved to fallback state file")
}
if pos, ok := fallbackLoaded.Strategies["rsi-eth"].Positions["ETH/USDC"]; !ok {
t.Error("ETH/USDC position should be preserved in fallback")
} else if pos.Quantity != 0.046044 {
t.Errorf("ETH position quantity = %f, want 0.046044", pos.Quantity)
}
}

// TestBackupStateFiles verifies that backup creates .bak files.
func TestBackupStateFiles(t *testing.T) {
dir := t.TempDir()
stateFile := filepath.Join(dir, "state.json")

// Create a state file.
state := NewAppState()
state.CycleCount = 42
SaveState(stateFile, state)

cfg := &Config{StateFile: stateFile}
BackupStateFiles(cfg)

// Verify .bak exists and has same content.
bakData, err := os.ReadFile(stateFile + ".bak")
if err != nil {
t.Fatalf("backup file not created: %v", err)
}
origData, _ := os.ReadFile(stateFile)
if string(bakData) != string(origData) {
t.Error("backup file content doesn't match original")
}
}

// TestLoadPlatformStatesFallbackOverride verifies that platform-specific state
// overrides fallback entries for the same strategy ID.
func TestLoadPlatformStatesFallbackOverride(t *testing.T) {
dir := t.TempDir()

// Fallback has an older version of alpaca-sma-spy.
fallbackPath := filepath.Join(dir, "state.json")
oldState := NewAppState()
oldState.Strategies["alpaca-sma-spy"] = &StrategyState{
ID: "alpaca-sma-spy", Platform: "alpaca", Cash: 500,
Positions: make(map[string]*Position), OptionPositions: make(map[string]*OptionPosition),
TradeHistory: []Trade{},
}
SaveState(fallbackPath, oldState)

// Platform file has the newer version.
alpacaDir := filepath.Join(dir, "platforms", "alpaca")
os.MkdirAll(alpacaDir, 0755)
alpacaState := NewAppState()
alpacaState.Strategies["alpaca-sma-spy"] = &StrategyState{
ID: "alpaca-sma-spy", Platform: "alpaca", Cash: 900,
Positions: make(map[string]*Position), OptionPositions: make(map[string]*OptionPosition),
TradeHistory: []Trade{},
}
SaveState(filepath.Join(alpacaDir, "state.json"), alpacaState)

cfg := &Config{
StateFile: fallbackPath,
Platforms: map[string]*PlatformConfig{
"alpaca": {StateFile: filepath.Join(alpacaDir, "state.json")},
},
}

merged, err := LoadPlatformStates(cfg)
if err != nil {
t.Fatal(err)
}

// Platform-specific version should win (cash=900, not 500).
s := merged.Strategies["alpaca-sma-spy"]
if s.Cash != 900 {
t.Errorf("alpaca-sma-spy cash = %f, want 900 (platform file should override fallback)", s.Cash)
}
}
