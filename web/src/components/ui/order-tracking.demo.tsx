import { OrderTracking } from "@/components/ui/order-tracking"

const demoSteps = [
  { name: "Order Placed", timestamp: "2024-03-20 14:23", isCompleted: true },
  { name: "Order Confirmed", timestamp: "2024-03-20 14:30", isCompleted: true },
  { name: "Order Shipped", timestamp: "2024-03-21 09:45", isCompleted: true },
  { name: "Out for Delivery", timestamp: "2024-03-22 08:15", isCompleted: false },
  { name: "Delivered", timestamp: "Pending", isCompleted: false },
]

function OrderTrackingDemo() {
  return (
    <div className="space-y-8">
      <div>
        <OrderTracking steps={demoSteps} />
      </div>
    </div>
  )
}

export { OrderTrackingDemo }
