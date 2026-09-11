# Every iOS task for VELRO, from the terminal. Xcode never has to be open.
#
# `make run` always builds Debug, and Debug talks to the API on this Mac
# (`make api`), never to production: a stray tap in the simulator must not
# spend a real SMS.

SIM ?= iPhone 17
# Which app: `make run APP=driver` for VELRO Driver. The passenger's is the default.
APP ?= passenger
PROJECT = Velro.xcodeproj
ifeq ($(APP),driver)
SCHEME = VelroDriver
BUNDLE = af.velro.driver
else
SCHEME = VelroPassenger
BUNDLE = af.velro.passenger
endif
DERIVED = build
DEST = platform=iOS Simulator,name=$(SIM)
APP_PATH = $(DERIVED)/Build/Products/Debug-iphonesimulator/$(SCHEME).app

.PHONY: help project core-test build run ui-test api clean

help:
	@echo "make api        start the local API on :8000 (codes come back in the response)"
	@echo "make core-test  test VelroCore on the Mac -- seconds, no simulator"
	@echo "make build      build the passenger app for the simulator (APP=driver: the driver's)"
	@echo "make run        build, install and launch it on $(SIM)"
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

api:
	../backend/scripts/dev-api.sh

clean:
	rm -rf $(DERIVED) $(PROJECT) VelroCore/.build
