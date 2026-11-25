package mqtt

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"errors"
	"io"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func generateTestCerts(t *testing.T, dir string) (caFile, serverCertFile, serverKeyFile, clientCertFile, clientKeyFile, otherKeyFile string, caPool *x509.CertPool) {
	t.Helper()

	gen := func(cn string, isCA bool, extUsage []x509.ExtKeyUsage, dnsNames []string, ips []net.IP, parentCert *x509.Certificate, parentKey *ecdsa.PrivateKey) (string, string, *x509.Certificate, *ecdsa.PrivateKey) {
		key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		if err != nil {
			t.Fatalf("generate key %s: %v", cn, err)
		}
		serial, err := rand.Int(rand.Reader, big.NewInt(1<<62))
		if err != nil {
			t.Fatalf("serial %s: %v", cn, err)
		}
		tmpl := &x509.Certificate{
			SerialNumber:          serial,
			Subject:               pkix.Name{CommonName: cn},
			NotBefore:             time.Now().Add(-time.Hour),
			NotAfter:              time.Now().Add(24 * time.Hour),
			KeyUsage:              x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
			ExtKeyUsage:           extUsage,
			DNSNames:              dnsNames,
			IPAddresses:           ips,
			BasicConstraintsValid: true,
		}
		if isCA {
			tmpl.IsCA = true
			tmpl.KeyUsage |= x509.KeyUsageCertSign
		}
		pCert := tmpl
		pKey := key
		if parentCert != nil && parentKey != nil {
			pCert = parentCert
			pKey = parentKey
		}
		der, err := x509.CreateCertificate(rand.Reader, tmpl, pCert, &key.PublicKey, pKey)
		if err != nil {
			t.Fatalf("create cert %s: %v", cn, err)
		}
		parsed, err := x509.ParseCertificate(der)
		if err != nil {
			t.Fatalf("parse cert %s: %v", cn, err)
		}
		cPath := filepath.Join(dir, cn+".crt")
		kPath := filepath.Join(dir, cn+".key")
		if err := os.WriteFile(cPath, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), 0o600); err != nil {
			t.Fatalf("write cert %s: %v", cn, err)
		}
		kDER, err := x509.MarshalECPrivateKey(key)
		if err != nil {
			t.Fatalf("marshal key %s: %v", cn, err)
		}
		if err := os.WriteFile(kPath, pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: kDER}), 0o600); err != nil {
			t.Fatalf("write key %s: %v", cn, err)
		}
		return cPath, kPath, parsed, key
	}

	var caCert *x509.Certificate
	var caKey *ecdsa.PrivateKey
	caFile, _, caCert, caKey = gen("test-ca", true, nil, nil, nil, nil, nil)
	serverCertFile, serverKeyFile, _, _ = gen("localhost", false, []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}, []string{"localhost"}, []net.IP{net.ParseIP("127.0.0.1")}, caCert, caKey)
	clientCertFile, clientKeyFile, _, _ = gen("backend", false, []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}, nil, nil, caCert, caKey)
	_, otherKeyFile, _, _ = gen("other", false, []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}, nil, nil, caCert, caKey)

	caPool = x509.NewCertPool()
	caPool.AddCert(caCert)
	return
}

func TestBuildTLSConfig_ValidAndFailureModes(t *testing.T) {
	dir := t.TempDir()
	caFile, _, _, clientCertFile, clientKeyFile, otherKeyFile, caPool := generateTestCerts(t, dir)

	invalidPEM := filepath.Join(dir, "bad.pem")
	if err := os.WriteFile(invalidPEM, []byte("invalid-pem-content"), 0o600); err != nil {
		t.Fatalf("write bad pem: %v", err)
	}

	t.Run("valid mTLS files", func(t *testing.T) {
		tlsCfg, err := BuildTLSConfig(ClientAuthOptions{
			TLSEnabled: true,
			CAFile:     caFile,
			CertFile:   clientCertFile,
			KeyFile:    clientKeyFile,
			ServerName: "mqtt-tls",
		})
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if tlsCfg.MinVersion < tls.VersionTLS12 || tlsCfg.InsecureSkipVerify {
			t.Errorf("insecure TLS config settings: MinVersion=%d InsecureSkipVerify=%v", tlsCfg.MinVersion, tlsCfg.InsecureSkipVerify)
		}
		if tlsCfg.RootCAs == nil || len(tlsCfg.Certificates) != 1 || tlsCfg.ServerName != "mqtt-tls" {
			t.Errorf("unexpected TLS config fields: %+v", tlsCfg)
		}
	})

	t.Run("pre-built TLS config rejects InsecureSkipVerify and missing RootCAs", func(t *testing.T) {
		if _, err := BuildTLSConfig(ClientAuthOptions{
			TLSConfig: &tls.Config{InsecureSkipVerify: true, RootCAs: caPool},
		}); !errors.Is(err, ErrInvalidTLSConfig) {
			t.Errorf("expected ErrInvalidTLSConfig for InsecureSkipVerify, got %v", err)
		}
		if _, err := BuildTLSConfig(ClientAuthOptions{
			TLSConfig: &tls.Config{MinVersion: tls.VersionTLS12},
		}); !errors.Is(err, ErrInvalidTLSConfig) {
			t.Errorf("expected ErrInvalidTLSConfig for nil RootCAs, got %v", err)
		}
	})

	for _, tc := range []struct {
		name string
		auth ClientAuthOptions
	}{
		{name: "empty CA file", auth: ClientAuthOptions{TLSEnabled: true}},
		{name: "missing CA file", auth: ClientAuthOptions{TLSEnabled: true, CAFile: filepath.Join(dir, "missing.crt")}},
		{name: "invalid PEM CA", auth: ClientAuthOptions{TLSEnabled: true, CAFile: invalidPEM}},
		{name: "cert without key", auth: ClientAuthOptions{TLSEnabled: true, CAFile: caFile, CertFile: clientCertFile}},
		{name: "key without cert", auth: ClientAuthOptions{TLSEnabled: true, CAFile: caFile, KeyFile: clientKeyFile}},
		{name: "mismatched cert and key", auth: ClientAuthOptions{TLSEnabled: true, CAFile: caFile, CertFile: clientCertFile, KeyFile: otherKeyFile}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if _, err := BuildTLSConfig(tc.auth); !errors.Is(err, ErrInvalidTLSConfig) {
				t.Errorf("expected ErrInvalidTLSConfig, got %v", err)
			}
		})
	}
}

func TestSubscriber_BuildClientOptions_TLSAndAuth(t *testing.T) {
	dir := t.TempDir()
	caFile, _, _, clientCertFile, clientKeyFile, _, _ := generateTestCerts(t, dir)

	t.Run("tls URI without TLS config fails closed", func(t *testing.T) {
		sub := NewGatewayStatusSubscriber("tls://mqtt-tls:8883", nil, nil, nil, nil, nil)
		if _, err := sub.buildClientOptions(); !errors.Is(err, ErrInvalidTLSConfig) {
			t.Errorf("expected ErrInvalidTLSConfig, got %v", err)
		}
		if err := sub.Start(context.Background()); !errors.Is(err, ErrInvalidTLSConfig) {
			t.Errorf("expected Start to fail closed with ErrInvalidTLSConfig, got %v", err)
		}
	})

	t.Run("tcp URI with TLS config fails closed to prevent silent downgrade", func(t *testing.T) {
		sub := NewGatewayStatusSubscriber("tcp://mqtt-dev:1883", nil, nil, nil, nil, nil,
			WithClientAuth(ClientAuthOptions{CAFile: caFile}),
		)
		if _, err := sub.buildClientOptions(); !errors.Is(err, ErrInvalidTLSConfig) {
			t.Errorf("expected ErrInvalidTLSConfig, got %v", err)
		}
	})

	t.Run("password without username fails closed", func(t *testing.T) {
		sub := NewGatewayStatusSubscriber("tcp://mqtt-dev:1883", nil, nil, nil, nil, nil,
			WithCredentials("", "secret"),
		)
		if _, err := sub.buildClientOptions(); !errors.Is(err, ErrInvalidTLSConfig) {
			t.Errorf("expected ErrInvalidTLSConfig, got %v", err)
		}
	})

	t.Run("tls URI with valid mTLS and credentials sets paho ClientOptions", func(t *testing.T) {
		testCred := "test-only-mqtt-cred"
		auth := ClientAuthOptions{
			TLSEnabled: true,
			CAFile:     caFile,
			CertFile:   clientCertFile,
			KeyFile:    clientKeyFile,
			Username:   "backend",
		}
		auth.Password = testCred
		sub := NewGatewayStatusSubscriber("tls://mqtt-tls:8883", nil, nil, nil, nil, nil,
			WithClientAuth(auth),
		)
		opts, err := sub.buildClientOptions()
		if err != nil {
			t.Fatalf("unexpected error: %v", err)
		}
		if len(opts.Servers) != 1 || opts.Servers[0].Scheme != "tls" || opts.Servers[0].Host != "mqtt-tls:8883" {
			t.Errorf("unexpected broker servers: %v", opts.Servers)
		}
		if opts.TLSConfig == nil || opts.TLSConfig.RootCAs == nil || len(opts.TLSConfig.Certificates) != 1 {
			t.Errorf("expected configured TLSConfig with mTLS cert, got %+v", opts.TLSConfig)
		}
		if opts.Username != "backend" || opts.Password != testCred {
			t.Errorf("expected configured credentials on ClientOptions")
		}
	})
}

func TestSubscriber_RealTLSHandshake_mTLS(t *testing.T) {
	dir := t.TempDir()
	caFile, serverCertFile, serverKeyFile, clientCertFile, clientKeyFile, _, caPool := generateTestCerts(t, dir)

	serverCert, err := tls.LoadX509KeyPair(serverCertFile, serverKeyFile)
	if err != nil {
		t.Fatalf("load server cert: %v", err)
	}
	serverTLS := &tls.Config{
		MinVersion:   tls.VersionTLS12,
		Certificates: []tls.Certificate{serverCert},
		ClientCAs:    caPool,
		ClientAuth:   tls.RequireAndVerifyClientCert,
	}

	ln, err := tls.Listen("tcp", "127.0.0.1:0", serverTLS)
	if err != nil {
		t.Fatalf("tls.Listen: %v", err)
	}
	defer ln.Close()

	peerCN := make(chan string, 1)
	go func() {
		conn, acceptErr := ln.Accept()
		if acceptErr != nil {
			return
		}
		defer conn.Close()
		tlsConn := conn.(*tls.Conn)
		if hsErr := tlsConn.Handshake(); hsErr != nil {
			return
		}
		state := tlsConn.ConnectionState()
		if len(state.PeerCertificates) > 0 {
			peerCN <- state.PeerCertificates[0].Subject.CommonName
		}
		// Read MQTT CONNECT fixed header + remaining bytes, reply with MQTT v3.1.1 CONNACK (RC=0).
		buf := make([]byte, 256)
		_ = tlsConn.SetReadDeadline(time.Now().Add(2 * time.Second))
		_, _ = io.ReadAtLeast(tlsConn, buf, 2)
		_, _ = tlsConn.Write([]byte{0x20, 0x02, 0x00, 0x00})
		time.Sleep(100 * time.Millisecond)
	}()

	brokerURI := "tls://" + ln.Addr().String()
	sub := NewGatewayStatusSubscriber(brokerURI, nil, nil, nil, nil, nil,
		WithClientAuth(ClientAuthOptions{
			TLSEnabled: true,
			CAFile:     caFile,
			CertFile:   clientCertFile,
			KeyFile:    clientKeyFile,
			ServerName: "localhost",
		}),
	)

	if err := sub.Start(context.Background()); err != nil {
		t.Fatalf("sub.Start failed: %v", err)
	}
	defer sub.Stop()

	select {
	case cn := <-peerCN:
		if cn != "backend" {
			t.Errorf("expected mTLS client CN 'backend', got %q", cn)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("timed out waiting for mTLS handshake")
	}
}
