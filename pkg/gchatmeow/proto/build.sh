#!/bin/sh
protoc --go_out=. --go_opt=paths=source_relative googlechat.proto
goimports -w googlechat.pb.go
