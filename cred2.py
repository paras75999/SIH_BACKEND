import json
import datetime
import os
import hashlib
import base64
import base58
import asyncio
from web3 import Web3
from dotenv import load_dotenv

# Using standard Python crypto libraries
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

# --- Part 1: Verifiable Credential Issuance Logic (Rewritten without DIDKit) ---

def generate_issuer_id():
    """
    Generates a new Ed25519 key pair and derives a did:key from it.
    """
    print("   - Generating new Ed25519 key pair...")
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    multicodec_prefix = bytes([0xed, 0x01])
    prefixed_public_bytes = multicodec_prefix + public_bytes
    did_key_identifier = base58.b58encode(prefixed_public_bytes).decode('utf-8')
    issuer_did = f"did:key:{did_key_identifier}"
    verification_method = f"{issuer_did}#{did_key_identifier}"
    
    print(f"   - Issuer DID created: {issuer_did}")
    return private_key, issuer_did, verification_method

def create_signed_vc(tourist_data, issuer_private_key, issuer_did, verification_method):
    """
    Creates and signs a Verifiable Credential using the cryptography library.
    """
    print("   - Constructing credential payload...")
    credential_payload = {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "id": "urn:uuid:4f378344-8596-4c3a-a978-8fcaba3903c5",
        "type": ["VerifiableCredential", "TouristCredential"],
        "issuer": issuer_did,
        "issuanceDate": datetime.datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        "credentialSubject": {
            "id": f"did:example:{hashlib.sha256(tourist_data['passportNumber'].encode()).hexdigest()}",
            "touristInfo": {
                "type": "Tourist", "name": tourist_data['name'], "nationality": tourist_data['nationality'],
                "passportNumber": tourist_data['passportNumber'], "emergencyContact": tourist_data['emergencyContact'],
                "bloodType": tourist_data['bloodType'], "insurancePolicyId": tourist_data['insurancePolicyId']
            }
        }
    }

    print("   - Manually creating JWS with cryptography library...")
    jws_header = {"alg": "EdDSA", "b64": False, "crit": ["b64"]}
    encoded_header = base64.urlsafe_b64encode(json.dumps(jws_header).encode('utf-8')).rstrip(b'=')
    
    # This ensures a consistent data representation for signing and verification
    payload_bytes = json.dumps(credential_payload, separators=(',', ':'), sort_keys=True).encode('utf-8')
    signing_input = encoded_header + b'.' + payload_bytes
    
    signature = issuer_private_key.sign(signing_input)
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b'=')
    
    detached_jws = f"{encoded_header.decode('utf-8')}..{encoded_signature.decode('utf-8')}"
    
    final_vc = credential_payload.copy()
    final_vc['proof'] = {
        "type": "Ed25519Signature2018",
        "created": datetime.datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        "verificationMethod": verification_method,
        "proofPurpose": "assertionMethod",
        "jws": detached_jws
    }
    
    print("   - ✅ SUCCESS: Credential issued and signed!")
    return json.dumps(final_vc)


# --- CORRECTED ORCHESTRATION FUNCTION ---
async def issue_tourist_credential(tourist_data):
    """
    Orchestrates the key generation and signing process. This is the main function
    called by the Flask API server.
    """
    try:
        # Step 1: Generate the issuer's complete identity
        private_key, issuer_did, verification_method = generate_issuer_id()

        # Step 2: Correctly pass all parts of the identity to the signing function
        signed_vc_string = create_signed_vc(
            tourist_data,
            private_key,
            issuer_did,
            verification_method
        )
        return signed_vc_string
    except Exception as e:
        error_message = f"Credential issuance failed in engine: {e}"
        print(f"   ❌ ERROR: {error_message}")
        raise Exception(error_message)


# --- Part 2: Blockchain Anchoring Logic (Unchanged) ---
def anchor_vc(vc_string):
    """
    Calculates a canonical hash of the VC and sends it to the smart contract.
    """
    print("   - Connecting to the blockchain...")
    load_dotenv()
    RPC_URL = os.getenv('RPC_URL')
    PRIVATE_KEY = os.getenv('DEPLOYER_PRIVATE_KEY')
    
    if not RPC_URL or not PRIVATE_KEY:
        raise Exception("RPC_URL or DEPLOYER_PRIVATE_KEY not found in .env file.")

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    account = w3.eth.account.from_key(PRIVATE_KEY)
    
    try:
        with open('anchor_address.txt', 'r') as f:
            contract_address = f.read().strip()
        with open('anchor_abi.json', 'r') as f:
            contract_abi = json.load(f)
    except FileNotFoundError as e:
        raise Exception(f"Could not find {e.filename}. Deploy contract first.")

    contract = w3.eth.contract(address=contract_address, abi=contract_abi)
    print(f"   - Loaded contract from: {contract_address}")
    
    vc_json = json.loads(vc_string)
    canonical_vc_string = json.dumps(vc_json, separators=(',', ':'), sort_keys=True)
    vc_bytes = canonical_vc_string.encode('utf-8')
    vc_hash = hashlib.sha256(vc_bytes).digest()
    print(f"   - Calculated Canonical Hash: {vc_hash.hex()}")

    try:
        print("   - Sending anchor transaction...")
        nonce = w3.eth.get_transaction_count(account.address)
        tx = contract.functions.anchor(vc_hash).build_transaction({
            'from': account.address, 'nonce': nonce, 'gas': 100000,
            'gasPrice': w3.to_wei('10', 'gwei')
        })
        
        signed_tx = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        
        print(f"   - Waiting for transaction receipt (TX Hash: {w3.to_hex(tx_hash)})...")
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        print(f"   - ✅ SUCCESS: Transaction confirmed in block {receipt.blockNumber}!")
        return w3.to_hex(tx_hash)
    except Exception as e:
        raise Exception(f"Transaction failed: {e}")

def save_vc_to_file(vc_string, filename="latest_vc_for_responder.json"):
    """Saves the VC string to a pretty-printed JSON file."""
    try:
        vc_json = json.loads(vc_string)
        with open(filename, "w") as f:
            json.dump(vc_json, f, indent=4)
        print(f"   - For reference, VC saved to '{filename}'")
    except Exception as e:
        print(f"   - ⚠️  Warning: Could not save VC to file: {e}")


# --- Main execution block for testing ---
async def main():
    """
    A simple test function to issue and anchor a sample credential.
    """
    print("===================================================")
    print("  Testing the Tourist Credential Engine (No DIDKit)")
    print("===================================================")
    
    sample_tourist_data = {
        "name": "Priya Sharma", "nationality": "British", "passportNumber": "G987654321",
        "emergencyContact": "+44 20 7946 0999", "bloodType": "O+", "insurancePolicyId": "INS-AETNA-5588-XYZ"
    }

    print("\nStep 1: Issuing a new TouristCredential...")
    try:
        # The test now calls the same main function as the API
        issued_vc = await issue_tourist_credential(sample_tourist_data)
        
        print("\nStep 2: Anchoring the new credential...")
        tx_hash = anchor_vc(issued_vc)
        
        print(f"\n✅ Engine Test Complete. Anchored with TX Hash: {tx_hash}")
        save_vc_to_file(issued_vc)
    except Exception as e:
        print(f"\n❌ Engine Test Failed. Reason: {e}")


if __name__ == "__main__":
    asyncio.run(main())

