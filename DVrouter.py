####################################################
# DVrouter.py
# Name: Hoang Gia Bao
# HUID: 23020653

# Name : Nguyen Ngoc Tai
# HUID : 23020701
#####################################################

from router import Router
from packet import Packet
import json
import copy

MAXIMUM = float('inf')

class DVrouter(Router):
    """Triển khai giao thức định tuyến Distance Vector (DV).

    Thêm các trường lớp và mã khởi tạo (ví dụ: để tạo bảng chuyển tiếp).
    Xem lớp cơ sở `Router` để biết chi tiết về các phương thức cần ghi đè.
    """

    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)  # Khởi tạo lớp cơ sở - KHÔNG ĐƯỢC XÓA
        self.heartbeat_time = heartbeat_time  # Thời gian giữa các lần gửi heartbeat
        self.last_time = 0  # Thời gian lần cuối gửi heartbeat
        
        # Khởi tạo các cấu trúc dữ liệu
        self.neighbors = {}        # Từ cổng -> (địa chỉ hàng xóm, chi phí liên kết)
        self.dv = {addr: (0, addr)}  # Từ đích -> (chi phí, bước nhảy tiếp theo)
        self.neighbor_dvs = {}     # Từ địa chỉ hàng xóm -> {đích: chi phí}
        self.forwarding_table = {} # Từ đích -> cổng chuyển tiếp

    def handle_packet(self, port, packet):
        """Xử lý gói tin đến."""
        if packet.is_traceroute:
            # Xử lý gói tin traceroute (dữ liệu thông thường)
            dst = packet.dst_addr
            if dst in self.forwarding_table:
                out_port = self.forwarding_table[dst]  # Lấy cổng từ bảng chuyển tiếp
                self.send(out_port, packet)  # Gửi gói tin qua cổng tương ứng
        else:
            # Xử lý gói tin định tuyến (cập nhật vector khoảng cách)
            try:
                received_dv = json.loads(packet.content)  # Giải mã nội dung gói tin
            except:
                return  # Bỏ qua nếu gói tin không hợp lệ

            src = packet.src_addr
            self.neighbor_dvs[src] = received_dv  # Lưu vector khoảng cách của hàng xóm

            # Tính lại vector khoảng cách và cập nhật nếu cần
            changed = self._recompute_dv()
            if changed:
                self._update_forwarding_table()  # Cập nhật bảng chuyển tiếp
                self._broadcast_dv()  # Phát tán vector khoảng cách mới

    def handle_new_link(self, port, endpoint, cost):
        """Xử lý liên kết mới được thêm."""
        # Lưu thông tin liên kết mới
        self.neighbors[port] = (endpoint, cost)

        # Cập nhật vector khoảng cách nếu liên kết này cung cấp đường đi tốt hơn
        if endpoint not in self.dv or cost < self.dv[endpoint][0]:
            self.dv[endpoint] = (cost, endpoint)

        # Đảm bảo hàng xóm có mục trong neighbor_dvs
        if endpoint not in self.neighbor_dvs:
            self.neighbor_dvs[endpoint] = {}

        # Tính lại vector khoảng cách và cập nhật nếu cần
        changed = self._recompute_dv()
        if changed:
            self._update_forwarding_table()  # Cập nhật bảng chuyển tiếp
            self._broadcast_dv()  # Phát tán vector khoảng cách mới

    def handle_remove_link(self, port):
        """Xử lý liên kết bị xóa."""
        if port in self.neighbors:
            neighbor_addr, _ = self.neighbors[port]

            # Xóa hàng xóm và vector khoảng cách của họ
            del self.neighbors[port]
            if neighbor_addr in self.neighbor_dvs:
                del self.neighbor_dvs[neighbor_addr]

            # Tính lại vector khoảng cách và cập nhật nếu cần
            changed = self._recompute_dv()
            if changed:
                self._update_forwarding_table()  # Cập nhật bảng chuyển tiếp
                self._broadcast_dv()  # Phát tán vector khoảng cách mới

    def handle_time(self, time_ms):
        """Xử lý thời gian hiện tại."""
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            # Phát tán vector khoảng cách định kỳ
            self._broadcast_dv()

    def _broadcast_dv(self):
        """Phát tán vector khoảng cách tới tất cả hàng xóm."""
        # Chuẩn bị vector khoảng cách để gửi
        dv_to_send = {}
        for dest in self.dv:
            cost, _ = self.dv[dest]
            dv_to_send[dest] = cost

        content = json.dumps(dv_to_send)  # Chuyển thành JSON

        # Gửi vector khoảng cách tới từng hàng xóm
        for port in self.neighbors:
            neighbor_addr, _ = self.neighbors[port]
            pkt = Packet(Packet.ROUTING, self.addr, neighbor_addr, content)
            self.send(port, pkt)

    def _recompute_dv(self):
        """Tính lại các đường đi tốt nhất bằng thuật toán Bellman-Ford."""
        new_dv = {self.addr: (0, self.addr)}  # Khởi tạo với chính router này

        # Tập hợp tất cả các đích có thể đến
        destinations = set()
        destinations.update(self.dv.keys())
        for dv in self.neighbor_dvs.values():
            for dest in dv:
                destinations.add(dest)

        # Tính chi phí tốt nhất cho từng đích
        for dest in destinations:
            if dest == self.addr:
                continue

            best_cost = MAXIMUM
            best_next = None

            for port in self.neighbors:
                neighbor_addr, link_cost = self.neighbors[port]

                # Đường đi trực tiếp tới hàng xóm
                if neighbor_addr == dest:
                    if link_cost < best_cost:
                        best_cost = link_cost
                        best_next = neighbor_addr
                # Đường đi qua hàng xóm
                elif neighbor_addr in self.neighbor_dvs:
                    neighbor_dv = self.neighbor_dvs[neighbor_addr]
                    if dest in neighbor_dv:
                        total = link_cost + neighbor_dv[dest]
                        if total < best_cost:
                            best_cost = total
                            best_next = neighbor_addr

            # Lưu đường đi tốt nhất nếu tìm thấy
            if best_cost < MAXIMUM:
                new_dv[dest] = (best_cost, best_next)

        # Kiểm tra xem vector khoảng cách có thay đổi không
        changed = (new_dv != self.dv)
        self.dv = new_dv
        return changed

    def _update_forwarding_table(self):
        """Cập nhật bảng chuyển tiếp dựa trên vector khoảng cách hiện tại."""
        self.forwarding_table = {}

        for dest in self.dv:
            if dest == self.addr:
                continue
            cost, next_hop = self.dv[dest]

            for port in self.neighbors:
                neighbor_addr, _ = self.neighbors[port]
                if neighbor_addr == next_hop:
                    self.forwarding_table[dest] = port
                    break

    def __repr__(self):
        """Biểu diễn thông tin router để debug trong trình mô phỏng mạng."""
        lines = []
        lines.append("DVrouter(addr=" + self.addr + ")")

        lines.append("\nVector Khoảng Cách:")
        for dest in sorted(self.dv):
            cost, nhop = self.dv[dest]
            lines.append("  Đích: " + dest + ", Chi Phí: " + str(cost) + ", Bước Nhảy Tiếp Theo: " + nhop)

        lines.append("\nBảng Chuyển Tiếp:")
        for dest in sorted(self.forwarding_table):
            port = self.forwarding_table[dest]
            lines.append("  Đích: " + dest + ", Cổng Ra: " + str(port))

        lines.append("\nHàng Xóm:")
        for port in self.neighbors:
            addr, cost = self.neighbors[port]
            lines.append("  Cổng: " + str(port) + ", Địa Chỉ: " + addr + ", Chi Phí: " + str(cost))

        return "\n".join(lines)