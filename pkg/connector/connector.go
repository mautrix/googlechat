package connector

import (
	"context"

	"go.mau.fi/util/configupgrade"
	"maunium.net/go/mautrix/bridgev2"
	"maunium.net/go/mautrix/bridgev2/database"
)

type GChatConnector struct {
	Bridge *bridgev2.Bridge
}

var (
	_ bridgev2.NetworkConnector = (*GChatConnector)(nil)
)

func (gc *GChatConnector) Init(bridge *bridgev2.Bridge) {
	gc.Bridge = bridge
}

func (gc *GChatConnector) Start(ctx context.Context) error {
	return nil
}

func (gc *GChatConnector) GetName() bridgev2.BridgeName {
	return bridgev2.BridgeName{
		DisplayName:      "Google Chat",
		NetworkURL:       "https://chat.google.com",
		NetworkIcon:      "mxc://maunium.net/BDIWAQcbpPGASPUUBuEGWXnQ",
		NetworkID:        "googlechat",
		BeeperBridgeType: "googlechat",
		DefaultPort:      29320,
	}
}

func (gc *GChatConnector) GetCapabilities() *bridgev2.NetworkGeneralCapabilities {
	return &bridgev2.NetworkGeneralCapabilities{}
}

func (gc *GChatConnector) GetBridgeInfoVersion() (info, caps int) {
	return 1, 1
}

func (gc *GChatConnector) GetConfig() (example string, data any, upgrader configupgrade.Upgrader) {
	return "", nil, nil
}

func (gc *GChatConnector) GetDBMetaTypes() database.MetaTypes {
	return database.MetaTypes{
		Portal: func() any {
			return &PortalMetadata{}
		},
		Ghost:    nil,
		Message:  nil,
		Reaction: nil,
		UserLogin: func() any {
			return &UserLoginMetadata{}
		},
	}
}
