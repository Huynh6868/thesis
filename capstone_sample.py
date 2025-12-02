import simpy
class Order:
   def __init__(self,env):
       self.env = env
       self.order_queue = [1,2,3,4,5,6,7]  # a list that holds the IDs of received orders, each time an order is received, it is added to the list !!
       self.picking_type = ['pick_by_order', 'pick_by_batch', 'pick_by_batch', 'pick_by_order', 'pick_by_batch', 'pick_by_batch', 'pick_by_batch']
       self.order_type = ['SIO', 'SIO', 'MIO', 'MIO', 'MIO', 'SIO', 'MIO']
       self.due_date = [15,20,25,30,35,40,45] # unit : minutes


       self.batch_id = [0,1,1,0,1,2,2] # if pick-by-order >> batch_id = 0, if pick-by-batch >> batch_id = the ID of that batch
       self.number_in_batch = [0,3,3,0,3,2,2] # number of orders in a batch




class WarehouseSimulation:
   def __init__(self, env, order_attributes, max_number_of_batches = 99):
       self.env = env


       self.order_attributes = order_attributes
       self.dummy_batch = []


       self.max_number_of_batches = max_number_of_batches
       self.batch = [[] for _ in range (max_number_of_batches)] # create a list of empty batches


       self.operators = simpy.Resource(env, capacity=20) # what is operators here mean ?? >> operators here are PICKERS
       self.packing_stations = simpy.Resource(env, capacity=20)
       self.picking_time_order_SIO = 2 # 2 min per SIO order
       self.picking_time_order_MIO = 7
       self.picking_time_batch_SIO = 5 # 7 min per order
       self.picking_time_batch_MIO = 10
       self.packing_time_SIO = 3
       self.packing_time_MIO = 7
       self.ready_to_ship = 1 # 1 min prepare for shipping
       self.orders_processed = 0
       self.late_orders = 0
       self.current_time = 0




   def arriving_procedure(self):
       while True: # make sure the procedure will continuously simulate the arrival of new orders.
           yield self.env.timeout(1)  # 1 is the inter-arrival time of received orders !!


           if self.order_attributes.order_queue: # Check if there are orders left
               # Logic for receiving orders and processing them
               order = self.receive_order()
               print (f"Order : {order}")
               self.env.process(self.order_manager(order))
           else:
               print("No more orders to process.")
               break  # Exit the loop if there are no more orders




   def receive_order(self):
       while self.order_attributes.order_queue: # Process orders until the orders_queue is empty


           #Assign attributes for the current order:
           current_order_id = self.order_attributes.order_queue.pop(0)
           # >> it takes the value of the first member in order_queue list, and also remove it out of the list
           current_order_type = self.order_attributes.order_type.pop(0)
           current_picking_type = self.order_attributes.picking_type.pop(0)
           current_batch_id = self.order_attributes.batch_id.pop(0)
           current_number_in_batch = self.order_attributes.number_in_batch.pop(0)
           current_due_date = self.order_attributes.due_date.pop(0)


           print(f"1. Received order {current_order_id} at time {self.env.now}")
           return current_order_id, current_order_type, current_picking_type, current_batch_id, current_number_in_batch, current_due_date
           # >> they act like an output of the caller receive_order
           # >> return as a TUPLE (current_order_id, current_order_type, current_picking_type, current_pick_stt,current_number_in_batch)




   def order_manager(self, order):
       yield self.env.timeout(1)
       # >> Simulate processing time (time to process the order after being received,
       #the process can be checking, validate, ...)


       # Classify the order is pick-by-order or pick-by-batch
       if order[2] == 'pick_by_order':
           print(f"Processing order {order[0]} at time {self.env.now}")
           self.env.process(self.picking_an_order(order)) #start the picking process (for pick-by-order)
       else:
           print(f"Processing batch {order[3]} with order {order[0]} at time {self.env.now} ")


           # Assign orders to their batch
           self.dummy_batch.append(order)  # Always add the order to the dummy batch


           # Check if we have enough orders to process the batch
           if len(self.dummy_batch) >= order[4]:  # Check if we have enough orders
               print(f"Batch {self.dummy_batch[0][3]} is completed and ready to be picked!")
               print(f"Batch {self.dummy_batch[0][3]} is : {self.dummy_batch}")
               self.env.process(self.received_batch())  # Process the batch




   def received_batch (self):
       for i in range (self.max_number_of_batches):
           if len (self.batch[i]) == 0 :
               self.batch[i] = self.dummy_batch.copy()
               # >> batch [i] (list) have multiple orders (tuple), each tuple contains attributes of each order
               self.dummy_batch.clear()
               print (f"Batch[i] is : {self.batch[i]}")
               yield self.env.timeout(0)
               self.env.process(self.picking_a_batch(i))  # start the picking process (for pick-by-batch)
               return
               # >> to stop the caller received_batch after it can assign to an empty batch : use "return" keyword




   def picking_an_order(self, order):
       with self.operators.request() as req: # request a picker for this process
           yield req


           if order[1] == 'SIO':
               yield self.env.timeout(self.picking_time_order_SIO)  # Picking time of SIO order
           else:
               yield self.env.timeout(self.picking_time_order_MIO)
           print(f"Order {order[0]} completed picking at time {self.env.now}")
           print(f"Available pickers are {self.operators.capacity} people")
           self.env.process(self.packing_for_order(order))  # start to process of packing




   def picking_a_batch(self, batch_index):
       # >> "i" of a caller received_batch and "batch_index" in a caller "picking_a_batch" have the same value


       with self.operators.request() as req:
           yield req


           print (f"Batch[batch_index] is {self.batch[batch_index]}")
           for current_order in self.batch[batch_index]: #with "current_order" stands for each order (tuple) in a batch
               if current_order[1] == 'SIO':
                   yield self.env.timeout(self.picking_time_batch_SIO)
                   print (f"Order {current_order[0]} (SIO) is picked at time {self.env.now}")
               else:
                   yield self.env.timeout(self.picking_time_batch_MIO)
                   print (f"Order {current_order[0]} (MIO) is picked at time {self.env.now}")
               print (f"Batch {current_order[3]} completed picking at time {self.env.now}")
           self.env.process(self.packing_for_batch(batch_index))  # start to process of packing




   def packing_for_order(self, order):
       with self.packing_stations.request() as req:
           yield req
           print(f"Available packers are {self.packing_stations.capacity} people")


           if order[1] == 'SIO':
               yield self.env.timeout(self.packing_time_SIO)
           else:
               yield self.env.timeout(self.packing_time_MIO)
           print(f"Order {order[0]} packed at time {self.env.now}")
           print(f"Available packers are {self.packing_stations.capacity} people")
           self.env.process(self.shipping(order)) #start the shipping process




   def packing_for_batch(self, x):
       # >> "batch_index" in a caller picking_a_batch and "x" in a caller packing_for_batch have the same value


       with self.packing_stations.request() as req:
           yield req


           print (f"Batch[x] is : {self.batch[x]}")
           for b in self.batch[x]: # "b" stands for each order (tuple) of batch[x]
               if b[1] == 'SIO':
                   yield self.env.timeout(self.packing_time_SIO)
                   print(f"Order {b[0]} packed at time {self.env.now}")
                   self.env.process(self.shipping(b))  # start the shipping process
               else:
                   yield self.env.timeout(self.packing_time_MIO)
                   print (f"Order {b[0]} packed at time {self.env.now}")
                   self.env.process(self.shipping(b))  # start the shipping process
               # when order {i} starts the shipping process, order {i+1} can start packing process simultaneously
           self.batch[x].clear()
           print(f"Available packers are {self.packing_stations.capacity} people")




   def shipping(self, order):
       yield self.env.timeout(self.ready_to_ship)  # Simulate shipping preparation time
       print(f"Order {order[0]} shipped at time {self.env.now}")


       # Check whether this order is tardy or not ?!
       if self.env.now > order[5]:
           self.late_orders += 1
           print (f"Order {order[0]} is tardy !")
       else:
           print (f"Order {order[0]} is shipped on time !")
       self.orders_processed += 1 # increase the number of processed orders by 1 unit




def run_simulation():
   env = simpy.Environment()


   # create an instance in the Order class
   order_attributes = Order(env)


   # create an instance in the WarehouseSimulation class with order_attributes
   warehouse = WarehouseSimulation(env, order_attributes)


   # Start the arriving procedure
   env.process(warehouse.arriving_procedure())


   # Run the simulation for a certain time
   env.run(until=150)


# to ensure that certain code only runs when the script is executed directly, not being imported from another script :
if __name__ == "__main__":
   run_simulation()
