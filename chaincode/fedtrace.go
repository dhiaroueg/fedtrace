// Chaincode FedTrace (Hyperledger Fabric, Go).
// ATTENTION : écrit pour porter les règles de anchoring/ledger.py ; non compilé ni exécuté dans
// l'environnement de génération. À compiler, tester (stub de simulation) puis déployer sur le réseau Fabric.
// Convention d'identité : MSP ID "<clinique>MSP" (ex. clinicAMSP) et "aggregatorMSP".
package main

import (
	"encoding/json"
	"fmt"
	"strings"

	"github.com/hyperledger/fabric-contract-api-go/contractapi"
)

type FedTrace struct{ contractapi.Contract }

type Contribution struct {
	Round       int                    `json:"round"`
	Clinic      string                 `json:"clinic"`
	Fingerprint string                 `json:"fingerprint"`
	Samples     int                    `json:"samples"`
	Privacy     map[string]interface{} `json:"privacy"`
	BaseModel   string                 `json:"base_model"`
	Timestamp   int64                  `json:"ts"`
}

type Rejected struct {
	Clinic string  `json:"clinic"`
	Reason string  `json:"reason"`
	Score  float64 `json:"score"`
}

type Model struct {
	Round       int                `json:"round"`
	Fingerprint string             `json:"fingerprint"`
	Strategy    string             `json:"strategy"`
	Kept        []string           `json:"kept"`
	Rejected    []Rejected         `json:"rejected"`
	Metrics     map[string]float64 `json:"metrics"`
	Parent      string             `json:"parent"`
	Timestamp   int64              `json:"ts"`
}

type Decision struct {
	DecisionID    string  `json:"decision_id"`
	ModelFP       string  `json:"model_fp"`
	ExplanationFP string  `json:"explanation_fp"`
	Clinic        string  `json:"clinic"`
	Case          string  `json:"case"`
	Probability   float64 `json:"probability"`
	Status        string  `json:"status"`
	Timestamp     int64   `json:"ts"`
}

func caller(ctx contractapi.TransactionContextInterface) (string, error) {
	msp, err := ctx.GetClientIdentity().GetMSPID()
	if err != nil {
		return "", err
	}
	return strings.TrimSuffix(msp, "MSP"), nil
}

func txTime(ctx contractapi.TransactionContextInterface) int64 {
	t, _ := ctx.GetStub().GetTxTimestamp() // horodatage de la transaction : déterministe entre pairs
	return t.Seconds
}

func get(ctx contractapi.TransactionContextInterface, key string, out interface{}) (bool, error) {
	b, err := ctx.GetStub().GetState(key)
	if err != nil {
		return false, err
	}
	if b == nil {
		return false, nil
	}
	return true, json.Unmarshal(b, out)
}

func put(ctx contractapi.TransactionContextInterface, key string, v interface{}) error {
	b, err := json.Marshal(v)
	if err != nil {
		return err
	}
	return ctx.GetStub().PutState(key, b)
}

func (c *FedTrace) AnchorContribution(ctx contractapi.TransactionContextInterface, js string) error {
	var r Contribution
	if err := json.Unmarshal([]byte(js), &r); err != nil {
		return err
	}
	id, err := caller(ctx)
	if err != nil {
		return err
	}
	if id != r.Clinic {
		return fmt.Errorf("identité %s différente de la clinique %s", id, r.Clinic)
	}
	key := fmt.Sprintf("CONTRIB~%d~%s", r.Round, r.Clinic)
	var old Contribution
	if ok, err := get(ctx, key, &old); err != nil {
		return err
	} else if ok {
		if old.Fingerprint == r.Fingerprint {
			return nil // idempotent
		}
		return fmt.Errorf("contribution déjà ancrée avec une autre empreinte")
	}
	var rk string
	if ok, _ := get(ctx, fmt.Sprintf("ROUND~%d", r.Round), &rk); ok {
		return fmt.Errorf("round clos : ancrage tardif refusé")
	}
	r.Timestamp = txTime(ctx)
	return put(ctx, key, r)
}

func (c *FedTrace) AnchorModel(ctx contractapi.TransactionContextInterface, js string) error {
	var m Model
	if err := json.Unmarshal([]byte(js), &m); err != nil {
		return err
	}
	id, err := caller(ctx)
	if err != nil {
		return err
	}
	if id != "aggregator" {
		return fmt.Errorf("seul l'agrégateur ancre un modèle")
	}
	rkey := fmt.Sprintf("ROUND~%d", m.Round)
	var existing string
	if ok, err := get(ctx, rkey, &existing); err != nil {
		return err
	} else if ok {
		if existing == m.Fingerprint {
			return nil
		}
		return fmt.Errorf("un modèle existe déjà pour ce round")
	}
	if m.Round == 0 {
		if m.Parent != "" {
			return fmt.Errorf("le modèle initial n'a pas de parent")
		}
	} else {
		var p Model
		if ok, err := get(ctx, "MODEL~"+m.Parent, &p); err != nil {
			return err
		} else if !ok || p.Round != m.Round-1 {
			return fmt.Errorf("parent inexistant ou round incohérent")
		}
	}
	cited := append([]string{}, m.Kept...)
	for _, r := range m.Rejected {
		cited = append(cited, r.Clinic)
	}
	for _, cl := range cited {
		var x Contribution
		if ok, err := get(ctx, fmt.Sprintf("CONTRIB~%d~%s", m.Round, cl), &x); err != nil {
			return err
		} else if !ok {
			return fmt.Errorf("contribution de %s absente du round %d", cl, m.Round)
		}
	}
	m.Timestamp = txTime(ctx)
	if err := put(ctx, "MODEL~"+m.Fingerprint, m); err != nil {
		return err
	}
	return put(ctx, rkey, m.Fingerprint)
}

func (c *FedTrace) AnchorDecision(ctx contractapi.TransactionContextInterface, js string) error {
	var d Decision
	if err := json.Unmarshal([]byte(js), &d); err != nil {
		return err
	}
	id, err := caller(ctx)
	if err != nil {
		return err
	}
	if id != d.Clinic {
		return fmt.Errorf("identité différente de la clinique émettrice")
	}
	var m Model
	if ok, err := get(ctx, "MODEL~"+d.ModelFP, &m); err != nil {
		return err
	} else if !ok {
		return fmt.Errorf("modèle inconnu")
	}
	if b, _ := ctx.GetStub().GetState("REVOKED~" + d.ModelFP); b != nil {
		return fmt.Errorf("modèle révoqué")
	}
	key := "DEC~" + d.DecisionID
	if b, _ := ctx.GetStub().GetState(key); b != nil {
		return fmt.Errorf("décision déjà ancrée")
	}
	d.Timestamp = txTime(ctx)
	return put(ctx, key, d)
}

func (c *FedTrace) RevokeModel(ctx contractapi.TransactionContextInterface, fp string, reason string) error {
	if id, err := caller(ctx); err != nil || id != "aggregator" {
		return fmt.Errorf("seul l'agrégateur révoque un modèle")
	}
	return put(ctx, "REVOKED~"+fp, map[string]string{"reason": reason})
}

// VerifyModel retourne l'enregistrement du modèle, ou une erreur s'il est inconnu ou révoqué.
func (c *FedTrace) VerifyModel(ctx contractapi.TransactionContextInterface, fp string) (*Model, error) {
	if b, _ := ctx.GetStub().GetState("REVOKED~" + fp); b != nil {
		return nil, fmt.Errorf("modèle révoqué")
	}
	var m Model
	if ok, err := get(ctx, "MODEL~"+fp, &m); err != nil {
		return nil, err
	} else if !ok {
		return nil, fmt.Errorf("modèle non certifié")
	}
	return &m, nil
}

func (c *FedTrace) VerifyDecision(ctx contractapi.TransactionContextInterface, id string) (*Decision, error) {
	var d Decision
	if ok, err := get(ctx, "DEC~"+id, &d); err != nil {
		return nil, err
	} else if !ok {
		return nil, fmt.Errorf("décision inconnue")
	}
	return &d, nil
}

// GetModelProvenance remonte la chaîne des modèles parents jusqu'au modèle initial.
func (c *FedTrace) GetModelProvenance(ctx contractapi.TransactionContextInterface, fp string) ([]Model, error) {
	var chain []Model
	for fp != "" {
		var m Model
		if ok, err := get(ctx, "MODEL~"+fp, &m); err != nil {
			return nil, err
		} else if !ok {
			return nil, fmt.Errorf("modèle %s inconnu", fp)
		}
		chain = append(chain, m)
		fp = m.Parent
	}
	return chain, nil
}

// GetKeyHistory : historique complet d'une clé (GetHistoryForKey).
func (c *FedTrace) GetKeyHistory(ctx contractapi.TransactionContextInterface, key string) ([]string, error) {
	it, err := ctx.GetStub().GetHistoryForKey(key)
	if err != nil {
		return nil, err
	}
	defer it.Close()
	var out []string
	for it.HasNext() {
		r, err := it.Next()
		if err != nil {
			return nil, err
		}
		out = append(out, fmt.Sprintf("%s|%s", r.TxId, string(r.Value)))
	}
	return out, nil
}

func main() {
	cc, err := contractapi.NewChaincode(&FedTrace{})
	if err != nil {
		panic(err)
	}
	if err := cc.Start(); err != nil {
		panic(err)
	}
}
