package gchatmeow

import (
	"reflect"
)

type Cookies struct {
	COMPASS string
	SSID    string
	SID     string
	OSID    string
	HSID    string
}

var (
	CookieNames = []string{"COMPASS", "SSID", "SID", "OSID", "HSID"}
)

// CookieIsDomainSpecific returns whether the name of a cookie is used
// on more than one Google subdomain, and therefore requires filtering
// the ingested cookies by domain.
func CookieIsDomainSpecific(cookieName string) bool {
	return cookieName == "COMPASS" || cookieName == "OSID"
}

func (c *Cookies) UpdateValues(values map[string]string) {
	r := reflect.ValueOf(c)
	for _, key := range CookieNames {
		field := reflect.Indirect(r).FieldByName(key)
		field.SetString(values[key])
	}
}
