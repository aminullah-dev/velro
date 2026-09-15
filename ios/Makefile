# Every iOS task for VELRO, from the terminal. Xcode never has to be open.
#
# `make run` always builds Debug, and Debug talks to the API on this Mac
# (`make api`), never to production: a stray tap in the simulator must not
# spend a real SMS.

SIM ?= iPhone 17
# Which app: `make run APP=driver` for VELRO Driver, `make run APP=ops` for
# VELRO Ops (or just `make ops`). The passenger's is the default.
APP ?= passenger
PROJECT = Velro.xcodeproj
ifeq ($(APP),driver)
SCHEME = VelroDriver
BUNDLE = af.velro.driver
else ifeq ($(APP),ops)
SCHEME = VelroOps
BUNDLE = af.velro.ops
else
SCHEME = VelroPassenger
BUNDLE = af.velro.passenger
endif
DERIVED = build
DEST = platform=iOS Simulator,name=$(SIM)
APP_PATH = $(DERIVED)/Build/Products/Debug-iphonesimulator/$(SCHEME).app
# VELRO Ops is also a Mac app, built from the same target.
MAC_APP_PATH = $(DERIVED)/Build/Products/Debug/VelroOps.app

.PHONY: help project core-test build run ops ops-mac-build ops-mac ui-test store-shots api clean

help:
	@echo "make api        start the local API on :8000 (codes come back in the response)"
	@echo "make core-test  test VelroCore on the Mac -- seconds, no simulator"
	@echo "make build      build the passenger app for the simulator (APP=driver or APP=ops: that one)"
	@echo "make run        build, install and launch it on $(SIM)"
	@echo "make ops        VELRO Ops on $(SIM) (the same as make run APP=ops)"
	@echo "make ops-mac    build VELRO Ops for this Mac and open it"
	@echo "make ui-test    sign in end to end in the simulator (needs make api)"
	@echo "make project    regenerate $(PROJECT) from project.yml"
	@echo "make clean      remove build output and the generated project"

project:
	xcodegen generate --quiet

core-test:
	cd VelroCore && swift test

build: project
	xcodebuild -project $(PROJECT) -scheme $(SCHEME) -configuration Debug \
		-destination '$(DEST)' -derivedDataPath $(DERIVED) -quiet build

run: build
	@xcrun simctl boot "$(SIM)" 2>/dev/null || true
	@open -a Simulator
	xcrun simctl install "$(SIM)" "$(APP_PATH)"
	xcrun simctl launch "$(SIM)" $(BUNDLE)

ops:
	$(MAKE) run APP=ops

# Debug, like everything here: the Mac build talks to `make api` too.
ops-mac-build: project
	xcodebuild -project $(PROJECT) -scheme VelroOps -configuration Debug \
		-destination 'platform=macOS' -derivedDataPath $(DERIVED) -quiet build

ops-mac: ops-mac-build
	open "$(MAC_APP_PATH)"

# The real app, driven in the simulator. Screenshots of every step land in
# build/ui-test.xcresult.
ui-test: project
	rm -rf $(DERIVED)/ui-test.xcresult
	@xcrun simctl boot "$(SIM)" 2>/dev/null || true
	@# Inside the service area: a Ghorband station (ایستگاه بابر), so the
	@# server's fence lets the ask through.
	xcrun simctl location "$(SIM)" set 34.961942,68.597052
	xcodebuild -project $(PROJECT) -scheme $(SCHEME) -configuration Debug \
		-destination '$(DEST)' -derivedDataPath $(DERIVED) \
		-resultBundlePath $(DERIVED)/ui-test.xcresult -quiet test

# The driver's App Store pictures (needs make api): a real trip in Dari on the
# 6.9" iPhone, a 9:41 status bar, the car on the Siahgird road just before a
# caution zone. Lands in AppStore/driver/screenshots as JPEG.
STORE_SIM ?= iPhone 17 Pro Max
store-shots: project
	rm -rf $(DERIVED)/store-shots.xcresult $(DERIVED)/store-shots
	@xcrun simctl boot "$(STORE_SIM)" 2>/dev/null || true
	xcrun simctl bootstatus "$(STORE_SIM)" -b >/dev/null
	xcrun simctl status_bar "$(STORE_SIM)" override --time 9:41 --dataNetwork wifi --wifiBars 3 --cellularBars 4 --batteryState charged --batteryLevel 100
	@# A fresh install asks; a test device may carry an old "Don't Allow".
	xcrun simctl privacy "$(STORE_SIM)" grant location af.velro.driver
	xcrun simctl location "$$(xcrun simctl list devices booted | grep '$(STORE_SIM) (' | head -1 | sed -E 's/.*\(([0-9A-F-]{36})\).*/\1/')" set 34.99896,68.83797
	TEST_RUNNER_VELRO_STORE_SHOTS=1 xcodebuild -project $(PROJECT) -scheme VelroDriver -configuration Debug \
		-destination 'platform=iOS Simulator,name=$(STORE_SIM)' -derivedDataPath $(DERIVED) \
		-resultBundlePath $(DERIVED)/store-shots.xcresult -only-testing:VelroDriverUITests/StoreScreenshots -quiet test
	xcrun xcresulttool export attachments --path $(DERIVED)/store-shots.xcresult --output-path $(DERIVED)/store-shots >/dev/null
	python3 scripts/store-shots.py $(DERIVED)/store-shots AppStore/driver/screenshots

api:
	../backend/scripts/dev-api.sh

clean:
	rm -rf $(DERIVED) $(PROJECT) VelroCore/.build
