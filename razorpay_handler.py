import razorpay
from config import settings

print("=" * 50)
print("RAZORPAY HANDLER LOADING...")
print(f"Key ID: {settings.RAZORPAY_KEY_ID}")
print(f"Key Secret length: {len(settings.RAZORPAY_KEY_SECRET)}")
print("=" * 50)

razorpay_client = razorpay.Client(
    auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
)

class RazorpayHandler:
    @staticmethod
    def create_order(amount_in_rupees, receipt_id, notes=None):
        try:
            order_data = {
                "amount": int(amount_in_rupees * 100),
                "currency": "INR",
                "receipt": receipt_id,
                "notes": notes or {}
            }
            order = razorpay_client.order.create(data=order_data)
            print(f"✓ Order created: {order['id']}")
            return order
        except Exception as e:
            print(f"❌ Order creation failed: {type(e).__name__}: {e}")
            return None
    
    @staticmethod
    def verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
        print("\n" + "=" * 50)
        print("SIGNATURE VERIFICATION DEBUG")
        print("=" * 50)
        print(f"Order ID:       {razorpay_order_id}")
        print(f"Payment ID:     {razorpay_payment_id}")
        print(f"Signature:      {razorpay_signature}")
        print(f"Key ID used:    {settings.RAZORPAY_KEY_ID}")
        print(f"Secret length:  {len(settings.RAZORPAY_KEY_SECRET)}")
        print("=" * 50)
        
        if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
            print("❌ Missing required field(s)")
            return False
        
        try:
            params_dict = {
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            }
            razorpay_client.utility.verify_payment_signature(params_dict)
            print("✓✓✓ SIGNATURE VERIFIED SUCCESSFULLY ✓✓✓")
            return True
        except razorpay.errors.SignatureVerificationError as e:
            print(f"❌ SIGNATURE MISMATCH")
            print(f"   Error: {e}")
            return False
        except Exception as e:
            print(f"❌ EXCEPTION: {type(e).__name__}")
            print(f"   Message: {e}")
            return False

razorpay_handler = RazorpayHandler()
