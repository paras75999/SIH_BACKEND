import json
import hashlib
import base64
import base58
import os
from web3 import Web3
from dotenv import load_dotenv

# Using standard Python crypto libraries
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature

def verify_vc_signature(vc_json):
    """
    Verifies the Ed25519Signature2018 on a Verifiable Credential.
    This is the counterpart to the create_signed_vc function.
    """
    try:
        # 1. Separate the proof from the main credential payload
        proof = vc_json.pop("proof")
        if not proof:
            print("   - Verification Error: No proof found in the credential.")
            return False

        # 2. Reconstruct the public key from the verificationMethod (did:key)
        verification_method = proof.get("verificationMethod")
        did_key_identifier = verification_method.split('#')[-1]
        prefixed_public_bytes = base58.b58decode(did_key_identifier)
        # Remove the 2-byte multicodec prefix (0xed01) to get the raw public key
        public_key_bytes = prefixed_public_bytes[2:]
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)

        # 3. Decode the JWS (JSON Web Signature)
        jws_string = proof.get("jws")
        encoded_header, _, encoded_signature = jws_string.split('.')
        
        # 4. Create the exact data that was originally signed (the signing input)
        #    This MUST match the canonicalization method used during signing.
        payload_bytes = json.dumps(vc_json, separators=(',', ':'), sort_keys=True).encode('utf-8')
        signing_input = encoded_header.encode('utf-8') + b'.' + payload_bytes

        # 5. Decode the signature
        #    We must add back the standard base64 padding
        decoded_signature = base64.urlsafe_b64decode(encoded_signature + '==')

        # 6. Perform the verification
        public_key.verify(decoded_signature, signing_input)
        
        print("   - ✅ Signature is cryptographically valid.")
        return True

    except InvalidSignature:
        print("   - ❌ Signature verification failed: The signature does not match the data.")
        return False
    except Exception as e:
        print(f"   - ❌ An unexpected error occurred during signature verification: {e}")
        return False


def verify_anchor(vc_string):
    """
    Checks if the credential's canonical hash is present on the blockchain.
    """
    try:
        load_dotenv()
        RPC_URL = os.getenv('RPC_URL')
        if not RPC_URL:
            raise Exception("RPC_URL not found in .env file.")

        w3 = Web3(Web3.HTTPProvider(RPC_URL))

        with open('anchor_address.txt', 'r') as f:
            contract_address = f.read().strip()
        with open('anchor_abi.json', 'r') as f:
            contract_abi = json.load(f)

        contract = w3.eth.contract(address=contract_address, abi=contract_abi)

        # Re-calculate the canonical hash in the exact same way as the engine
        vc_json = json.loads(vc_string)
        canonical_vc_string = json.dumps(vc_json, separators=(',', ':'), sort_keys=True)
        vc_bytes = canonical_vc_string.encode('utf-8')
        vc_hash = hashlib.sha256(vc_bytes).digest()

        print(f"   - Checking for hash on-chain: {vc_hash.hex()}")
        is_anchored = contract.functions.isAnchored(vc_hash).call()
        
        if is_anchored:
            print("   - ✅ Anchor found on the blockchain.")
        else:
            print("   - ⚠️  Anchor NOT FOUND on the blockchain.")
        return is_anchored

    except Exception as e:
        print(f"   - ❌ An error occurred during blockchain verification: {e}")
        return False

