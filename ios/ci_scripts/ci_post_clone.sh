#!/bin/sh
# Xcode Cloud runs this right after cloning. Velro.xcodeproj is generated from
# project.yml and is not in git (see project.yml), so without this step every
# archive fails with "Project Velro.xcodeproj does not exist at ios/Velro.xcodeproj".
set -eu
cd "$CI_PRIMARY_REPOSITORY_PATH/ios"
brew install xcodegen
xcodegen generate --spec project.yml
