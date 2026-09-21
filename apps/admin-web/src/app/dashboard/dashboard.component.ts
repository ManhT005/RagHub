import { ChangeDetectionStrategy, Component } from '@angular/core';
import { NzCardModule } from 'ng-zorro-antd/card';
import { NzIconModule } from 'ng-zorro-antd/icon';
import { NzTagModule } from 'ng-zorro-antd/tag';

@Component({
  selector: 'raghub-dashboard',
  imports: [NzCardModule, NzIconModule, NzTagModule],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent {
  protected readonly services = [
    { name: 'PostgreSQL', role: 'Metadata and workflow state', icon: 'database' },
    { name: 'Redis', role: 'Celery task broker', icon: 'cloud-server' },
    { name: 'Elasticsearch', role: 'Scoped BM25 retrieval', icon: 'database' },
    { name: 'MinIO', role: 'Original PDF storage', icon: 'file-text' },
  ];
}
