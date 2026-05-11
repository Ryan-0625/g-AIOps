package connection

import (
	"fmt"
	"net/http"
)

// AuthHeader is the HTTP header carrying the cluster token during WS upgrade.
const AuthHeader = "Authorization"

const authScheme = "Bearer"

// Auth holds the cluster token for Worker→Master authentication.
type Auth struct {
	token string
}

func NewAuth(token string) *Auth {
	return &Auth{token: token}
}

// Apply sets the Authorization header on an HTTP request.
func (a *Auth) Apply(req *http.Header) {
	req.Set(AuthHeader, fmt.Sprintf("%s %s", authScheme, a.token))
}

// Validate checks a token string.
func (a *Auth) Validate() error {
	if a.token == "" {
		return fmt.Errorf("cluster token must not be empty")
	}
	return nil
}
