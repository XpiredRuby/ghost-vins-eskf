import math, smbus, rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

A=0x68
GB=[-1.69879,-0.49876,-1.10303]
AB=0.98696

class W(Node):
    def __init__(self):
        super().__init__("ghost_imu_watchdog")
        self.b=smbus.SMBus(1)
        self.b.write_byte_data(A,0x6B,0)
        self.p=self.create_publisher(String,"/ghost/imu/watchdog_state",10)
        self.create_timer(0.1,self.tick)
    def r(self,reg):
        v=(self.b.read_byte_data(A,reg)<<8)|self.b.read_byte_data(A,reg+1)
        return v-65536 if v>32767 else v

    def tick(self):
        ax,ay,az=self.r(0x3B)/16384,self.r(0x3D)/16384,self.r(0x3F)/16384
        gx=self.r(0x43)/131-GB[0]; gy=self.r(0x45)/131-GB[1]; gz=self.r(0x47)/131-GB[2]
        an=math.sqrt(ax*ax+ay*ay+az*az); gm=math.sqrt(gx*gx+gy*gy+gz*gz)
        state="STABLE"
        if gm>25 or abs(an-AB)>0.12: state="CAMERA_BUMPED"
        elif gm>8 or abs(an-AB)>0.04: state="CAMERA_SUSPECT"
        msg=String(); msg.data=f"{state}, gyro_dps={gm:.2f}, accel_delta_g={abs(an-AB):.3f}"
        self.p.publish(msg)

def main():
    rclpy.init()
    n=W()
    try:
        rclpy.spin(n)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        n.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__=="__main__":
    main()
