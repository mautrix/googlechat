package connector

import (
	"context"
	"fmt"

	"maunium.net/go/mautrix/bridgev2"
	"maunium.net/go/mautrix/bridgev2/database"
	"maunium.net/go/mautrix/bridgev2/networkid"
	"maunium.net/go/mautrix/bridgev2/status"
	"maunium.net/go/mautrix/id"

	"go.mau.fi/mautrix-googlechat/pkg/gchatmeow"
)

const (
	LoginStepIDCookies  = "com.beeper.googlechat.login.cookies"
	LoginStepIDComplete = "com.beeper.googlechat.login.complete"
)

func (gc *GChatConnector) CreateLogin(ctx context.Context, user *bridgev2.User, flowID string) (bridgev2.LoginProcess, error) {
	return &GChatCookieLogin{User: user}, nil
}

func (gc *GChatConnector) GetLoginFlows() []bridgev2.LoginFlow {
	return []bridgev2.LoginFlow{{
		Name:        "Cookies",
		Description: "Log in with your cookies",
		ID:          "cookies",
	}}
}

func (gc *GChatConnector) LoadUserLogin(ctx context.Context, login *bridgev2.UserLogin) error {
	loginMetadata := login.Metadata.(*UserLoginMetadata)
	var client *gchatmeow.Client
	if loginMetadata.Cookies != nil {
		client = gchatmeow.NewClient(loginMetadata.Cookies, "", 0, 0)
	}
	login.Client = NewClient(login, client)
	return nil
}

type GChatCookieLogin struct {
	User *bridgev2.User
}

type UserLoginMetadata struct {
	Cookies *gchatmeow.Cookies
}

var _ bridgev2.LoginProcessCookies = (*GChatCookieLogin)(nil)

func (gl *GChatCookieLogin) Start(ctx context.Context) (*bridgev2.LoginStep, error) {
	fields := make([]bridgev2.LoginCookieField, 5)
	for i, key := range gchatmeow.CookieNames {
		fields[i] = bridgev2.LoginCookieField{
			ID:       key,
			Required: true,
			Sources: []bridgev2.LoginCookieFieldSource{
				{Type: bridgev2.LoginCookieTypeCookie, Name: key},
			},
		}
	}
	step := &bridgev2.LoginStep{
		Type:         bridgev2.LoginStepTypeCookies,
		StepID:       LoginStepIDCookies,
		Instructions: "Enter a JSON object with your cookies, or a cURL command copied from browser devtools.",
		CookiesParams: &bridgev2.LoginCookiesParams{
			URL:    "https://chat.google.com/",
			Fields: fields,
		},
	}
	return step, nil
}

func (gl *GChatCookieLogin) Cancel() {}

func (gl *GChatCookieLogin) SubmitCookies(ctx context.Context, strCookies map[string]string) (*bridgev2.LoginStep, error) {
	cookies := &gchatmeow.Cookies{}
	cookies.UpdateValues(strCookies)

	client := gchatmeow.NewClient(cookies, "", 0, 0)
	err := client.RefreshTokens(ctx)
	if err != nil {
		return nil, err
	}

	user, err := client.GetSelf(ctx)
	if err != nil {
		return nil, err
	}

	userId := user.UserId.Id
	ul, err := gl.User.NewLogin(ctx, &database.UserLogin{
		ID:         networkid.UserLoginID(userId),
		RemoteName: user.GetName(),
		RemoteProfile: status.RemoteProfile{
			Name:   user.GetName(),
			Email:  user.Email,
			Avatar: id.ContentURIString(user.GetAvatarUrl()),
		},
		Metadata: &UserLoginMetadata{
			Cookies: cookies,
		},
	}, nil)

	if err != nil {
		return nil, fmt.Errorf("failed to save new login: %w", err)
	}

	ul.Client.Connect(ctx)
	c := ul.Client.(*GChatClient)
	c.userLogin = ul
	c.client = client

	return &bridgev2.LoginStep{
		Type:         bridgev2.LoginStepTypeComplete,
		StepID:       LoginStepIDComplete,
		Instructions: fmt.Sprintf("Logged in as %s (%s)", user.GetName(), userId),
		CompleteParams: &bridgev2.LoginCompleteParams{
			UserLoginID: ul.ID,
			UserLogin:   ul,
		},
	}, nil
}
