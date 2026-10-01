import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { NzCardModule } from 'ng-zorro-antd/card';
import { NzIconModule, provideNzIconsPatch } from 'ng-zorro-antd/icon';
import { NzTagModule } from 'ng-zorro-antd/tag';
import { CloudServerOutline, DatabaseOutline, FileTextOutline, MessageOutline } from '@ant-design/icons-angular/icons';

@Component({
  selector: 'raghub-dashboard',
  imports: [NzCardModule, NzIconModule, NzTagModule, RouterLink],
  providers: [provideNzIconsPatch([CloudServerOutline, DatabaseOutline, FileTextOutline, MessageOutline])],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent {
  protected readonly services = [
    { name: 'PostgreSQL', role: 'Dữ liệu và trạng thái xử lý', icon: 'database' },
    { name: 'Redis', role: 'Hàng đợi tác vụ Celery', icon: 'cloud-server' },
    { name: 'Elasticsearch', role: 'Tìm kiếm trong phạm vi tổ chức', icon: 'database' },
    { name: 'MinIO', role: 'Lưu trữ tài liệu gốc', icon: 'file-text' },
  ];
}
