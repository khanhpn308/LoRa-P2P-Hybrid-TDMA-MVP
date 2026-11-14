package api_test

import (
	"testing"

	"github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api"
)

func TestRole_Constants(t *testing.T) {
	tests := []struct {
		name string
		got  api.Role
		want string
	}{
		{name: "RoleAdmin", got: api.RoleAdmin, want: "ADMIN"},
		{name: "RoleOperator", got: api.RoleOperator, want: "OPERATOR"},
		{name: "RoleViewer", got: api.RoleViewer, want: "VIEWER"},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			if string(tc.got) != tc.want {
				t.Errorf("expected %s constant to be %q, got %q", tc.name, tc.want, string(tc.got))
			}
		})
	}
}

func TestStaticAuthenticator_Nil(t *testing.T) {
	var a *api.StaticAuthenticator
	role, err := a.Authenticate("token")
	if err == nil {
		t.Errorf("expected error on nil authenticator")
	}
	if role != "" {
		t.Errorf("expected empty role on nil authenticator, got %q", role)
	}
	if err != nil && err.Error() != "unconfigured authenticator" {
		t.Errorf("expected 'unconfigured authenticator', got %q", err.Error())
	}
}

func TestStaticAuthenticator_Authenticate(t *testing.T) {
	configuredTokens := map[string]api.Role{
		"token-admin":    api.RoleAdmin,
		"token-operator": api.RoleOperator,
		"token-viewer":   api.RoleViewer,
	}

	tests := []struct {
		name          string
		authenticator *api.StaticAuthenticator
		token         string
		wantRole      api.Role
		wantErr       string
	}{
		{
			name:          "nil receiver",
			authenticator: nil,
			token:         "any-token",
			wantRole:      "",
			wantErr:       "unconfigured authenticator",
		},
		{
			name:          "nil tokens map",
			authenticator: api.NewStaticAuthenticator(nil),
			token:         "any-token",
			wantRole:      "",
			wantErr:       "unconfigured authenticator",
		},
		{
			name:          "empty non-nil tokens map",
			authenticator: api.NewStaticAuthenticator(map[string]api.Role{}),
			token:         "token-admin",
			wantRole:      "",
			wantErr:       "invalid or expired bearer token",
		},
		{
			name:          "valid ADMIN token",
			authenticator: api.NewStaticAuthenticator(configuredTokens),
			token:         "token-admin",
			wantRole:      api.RoleAdmin,
			wantErr:       "",
		},
		{
			name:          "valid OPERATOR token",
			authenticator: api.NewStaticAuthenticator(configuredTokens),
			token:         "token-operator",
			wantRole:      api.RoleOperator,
			wantErr:       "",
		},
		{
			name:          "valid VIEWER token",
			authenticator: api.NewStaticAuthenticator(configuredTokens),
			token:         "token-viewer",
			wantRole:      api.RoleViewer,
			wantErr:       "",
		},
		{
			name:          "unknown token",
			authenticator: api.NewStaticAuthenticator(configuredTokens),
			token:         "unknown-token",
			wantRole:      "",
			wantErr:       "invalid or expired bearer token",
		},
		{
			name:          "empty token string with configured map",
			authenticator: api.NewStaticAuthenticator(configuredTokens),
			token:         "",
			wantRole:      "",
			wantErr:       "invalid or expired bearer token",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			role, err := tc.authenticator.Authenticate(tc.token)
			if tc.wantErr == "" {
				if err != nil {
					t.Fatalf("expected no error, got %v", err)
				}
				if role != tc.wantRole {
					t.Errorf("expected role %q, got %q", tc.wantRole, role)
				}
			} else {
				if err == nil {
					t.Fatalf("expected error containing %q, got nil", tc.wantErr)
				}
				if err.Error() != tc.wantErr {
					t.Errorf("expected error %q, got %q", tc.wantErr, err.Error())
				}
				if role != "" {
					t.Errorf("expected zero-value empty role on error, got %q", role)
				}
			}
		})
	}
}
