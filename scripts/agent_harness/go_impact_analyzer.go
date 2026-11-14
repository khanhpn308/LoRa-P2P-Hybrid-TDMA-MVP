// scripts/agent_harness/go_impact_analyzer.go
// Trusted Go AST helper for conservative-first Go dependency impact analysis.
// Standard-library only: go/parser, go/token, go/ast, encoding/json, os, io.
package main

import (
	"encoding/json"
	"fmt"
	"go/ast"
	"go/parser"
	"go/token"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

const (
	CurrentSchemaVersion = 1
	MaxInputBytes        = 10 * 1024 * 1024 // 10 MB bound for JSON stdin
)

type InputPayload struct {
	SchemaVersion int               `json:"schema_version"`
	Module        string            `json:"module"`
	Files         map[string]string `json:"files"`
}

type ImportInfo struct {
	Path  string `json:"path"`
	Alias string `json:"alias"` // "" for default, "_" for blank, "." for dot, or custom alias
}

type SymbolInfo struct {
	Name     string `json:"name"`
	Kind     string `json:"kind"` // "type", "func", "const", "var"
	Exported bool   `json:"exported"`
}

type MethodInfo struct {
	ReceiverType string `json:"receiver_type"`
	Name         string `json:"name"`
	Exported     bool   `json:"exported"`
}

type SelectorRef struct {
	PackageAlias string `json:"package_alias"`
	Name         string `json:"name"`
}

type TypeDetail struct {
	HasEmbeddedFields bool `json:"has_embedded_fields"`
	IsAlias           bool `json:"is_alias"`
	HasGenerics       bool `json:"has_generics"`
}

type FileAnalysis struct {
	PackageName          string                `json:"package_name"`
	IsTest               bool                  `json:"is_test"`
	HasInitFunc          bool                  `json:"has_init_func"`
	HasPackageLevelVars  bool                  `json:"has_package_level_vars"`
	PackageLevelVarNames []string              `json:"package_level_var_names"`
	Imports              []ImportInfo          `json:"imports"`
	DeclaredSymbols      []SymbolInfo          `json:"declared_symbols"`
	DeclaredMethods      []MethodInfo          `json:"declared_methods"`
	SelectorRefs         []SelectorRef         `json:"selector_refs"`
	IdentRefs            []string              `json:"ident_refs"`
	TopLevelTypeDetails  map[string]TypeDetail `json:"top_level_type_details"`
	HasUnsafeOrCgo       bool                  `json:"has_unsafe_or_cgo"`
	HasDotImport         bool                  `json:"has_dot_import"`
	HasBlankImport       bool                  `json:"has_blank_import"`
	ParseError           string                `json:"parse_error,omitempty"`
}

type OutputPayload struct {
	SchemaVersion int                     `json:"schema_version"`
	Files         map[string]FileAnalysis `json:"files"`
}

func extractReceiverTypeName(expr ast.Expr) string {
	switch t := expr.(type) {
	case *ast.StarExpr:
		return extractReceiverTypeName(t.X)
	case *ast.Ident:
		return t.Name
	case *ast.IndexExpr:
		return extractReceiverTypeName(t.X)
	case *ast.IndexListExpr:
		return extractReceiverTypeName(t.X)
	default:
		return ""
	}
}

func analyzeSource(filename string, src string) FileAnalysis {
	res := FileAnalysis{
		IsTest:              strings.HasSuffix(filename, "_test.go"),
		TopLevelTypeDetails: make(map[string]TypeDetail),
		Imports:             make([]ImportInfo, 0),
		DeclaredSymbols:     make([]SymbolInfo, 0),
		DeclaredMethods:     make([]MethodInfo, 0),
		SelectorRefs:        make([]SelectorRef, 0),
		IdentRefs:           make([]string, 0),
	}

	fset := token.NewFileSet()
	f, err := parser.ParseFile(fset, filename, src, parser.ParseComments)
	if err != nil {
		res.ParseError = err.Error()
		return res
	}

	res.PackageName = f.Name.Name

	// Imports
	for _, imp := range f.Imports {
		path := strings.Trim(imp.Path.Value, `"`)
		alias := ""
		if imp.Name != nil {
			alias = imp.Name.Name
			if alias == "_" {
				res.HasBlankImport = true
			} else if alias == "." {
				res.HasDotImport = true
			}
		}
		if path == "unsafe" || path == "C" {
			res.HasUnsafeOrCgo = true
		}
		res.Imports = append(res.Imports, ImportInfo{
			Path:  path,
			Alias: alias,
		})
	}

	// Declarations
	for _, decl := range f.Decls {
		switch d := decl.(type) {
		case *ast.FuncDecl:
			if d.Recv == nil {
				// Package-level function
				name := d.Name.Name
				if name == "init" {
					res.HasInitFunc = true
				}
				res.DeclaredSymbols = append(res.DeclaredSymbols, SymbolInfo{
					Name:     name,
					Kind:     "func",
					Exported: ast.IsExported(name),
				})
			} else {
				// Method
				if len(d.Recv.List) > 0 {
					recvTypeName := extractReceiverTypeName(d.Recv.List[0].Type)
					res.DeclaredMethods = append(res.DeclaredMethods, MethodInfo{
						ReceiverType: recvTypeName,
						Name:         d.Name.Name,
						Exported:     ast.IsExported(d.Name.Name),
					})
				}
			}
		case *ast.GenDecl:
			switch d.Tok {
			case token.VAR:
				res.HasPackageLevelVars = true
				for _, spec := range d.Specs {
					if valSpec, ok := spec.(*ast.ValueSpec); ok {
						for _, name := range valSpec.Names {
							res.PackageLevelVarNames = append(res.PackageLevelVarNames, name.Name)
							res.DeclaredSymbols = append(res.DeclaredSymbols, SymbolInfo{
								Name:     name.Name,
								Kind:     "var",
								Exported: ast.IsExported(name.Name),
							})
						}
					}
				}
			case token.CONST:
				for _, spec := range d.Specs {
					if valSpec, ok := spec.(*ast.ValueSpec); ok {
						for _, name := range valSpec.Names {
							res.DeclaredSymbols = append(res.DeclaredSymbols, SymbolInfo{
								Name:     name.Name,
								Kind:     "const",
								Exported: ast.IsExported(name.Name),
							})
						}
					}
				}
			case token.TYPE:
				for _, spec := range d.Specs {
					if typeSpec, ok := spec.(*ast.TypeSpec); ok {
						name := typeSpec.Name.Name
						res.DeclaredSymbols = append(res.DeclaredSymbols, SymbolInfo{
							Name:     name,
							Kind:     "type",
							Exported: ast.IsExported(name),
						})
						detail := TypeDetail{
							IsAlias:     typeSpec.Assign.IsValid(),
							HasGenerics: typeSpec.TypeParams != nil && len(typeSpec.TypeParams.List) > 0,
						}
						if structType, ok := typeSpec.Type.(*ast.StructType); ok {
							for _, field := range structType.Fields.List {
								if len(field.Names) == 0 {
									detail.HasEmbeddedFields = true
								}
							}
						}
						res.TopLevelTypeDetails[name] = detail
					}
				}
			}
		}
	}

	// Selector expressions and identifier references
	selectorSet := make(map[string]bool)
	identSet := make(map[string]bool)
	ast.Inspect(f, func(n ast.Node) bool {
		switch node := n.(type) {
		case *ast.SelectorExpr:
			if ident, ok := node.X.(*ast.Ident); ok {
				key := ident.Name + "." + node.Sel.Name
				if !selectorSet[key] {
					selectorSet[key] = true
					res.SelectorRefs = append(res.SelectorRefs, SelectorRef{
						PackageAlias: ident.Name,
						Name:         node.Sel.Name,
					})
				}
			}
		case *ast.Ident:
			if !identSet[node.Name] {
				identSet[node.Name] = true
				res.IdentRefs = append(res.IdentRefs, node.Name)
			}
		}
		return true
	})

	// Deterministic sorting of results
	sort.Slice(res.Imports, func(i, j int) bool {
		if res.Imports[i].Path == res.Imports[j].Path {
			return res.Imports[i].Alias < res.Imports[j].Alias
		}
		return res.Imports[i].Path < res.Imports[j].Path
	})
	sort.Slice(res.DeclaredSymbols, func(i, j int) bool {
		return res.DeclaredSymbols[i].Name < res.DeclaredSymbols[j].Name
	})
	sort.Slice(res.DeclaredMethods, func(i, j int) bool {
		if res.DeclaredMethods[i].ReceiverType == res.DeclaredMethods[j].ReceiverType {
			return res.DeclaredMethods[i].Name < res.DeclaredMethods[j].Name
		}
		return res.DeclaredMethods[i].ReceiverType < res.DeclaredMethods[j].ReceiverType
	})
	sort.Slice(res.SelectorRefs, func(i, j int) bool {
		if res.SelectorRefs[i].PackageAlias == res.SelectorRefs[j].PackageAlias {
			return res.SelectorRefs[i].Name < res.SelectorRefs[j].Name
		}
		return res.SelectorRefs[i].PackageAlias < res.SelectorRefs[j].PackageAlias
	})
	sort.Strings(res.IdentRefs)
	sort.Strings(res.PackageLevelVarNames)

	return res
}

func main() {
	reader := io.LimitReader(os.Stdin, MaxInputBytes)
	data, err := io.ReadAll(reader)
	if err != nil {
		fmt.Fprintf(os.Stderr, "error reading stdin: %v\n", err)
		os.Exit(1)
	}

	var input InputPayload
	if err := json.Unmarshal(data, &input); err != nil {
		fmt.Fprintf(os.Stderr, "invalid input JSON: %v\n", err)
		os.Exit(2)
	}

	if input.SchemaVersion != CurrentSchemaVersion {
		fmt.Fprintf(os.Stderr, "unsupported schema version: %d (expected %d)\n", input.SchemaVersion, CurrentSchemaVersion)
		os.Exit(3)
	}

	output := OutputPayload{
		SchemaVersion: CurrentSchemaVersion,
		Files:         make(map[string]FileAnalysis),
	}

	for relPath, content := range input.Files {
		cleaned := filepath.Clean(relPath)
		if strings.HasPrefix(cleaned, "..") || filepath.IsAbs(cleaned) {
			output.Files[relPath] = FileAnalysis{
				ParseError: fmt.Sprintf("invalid relative path: %s", relPath),
			}
			continue
		}
		output.Files[relPath] = analyzeSource(relPath, content)
	}

	encoder := json.NewEncoder(os.Stdout)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(output); err != nil {
		fmt.Fprintf(os.Stderr, "error encoding output JSON: %v\n", err)
		os.Exit(4)
	}
}
