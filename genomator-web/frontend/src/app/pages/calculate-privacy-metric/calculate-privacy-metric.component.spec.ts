import { ComponentFixture, TestBed } from '@angular/core/testing';

import { CalculatePrivacyMetricComponent } from './calculate-privacy-metric.component';

describe('CalculatePrivacyMetricComponent', () => {
  let component: CalculatePrivacyMetricComponent;
  let fixture: ComponentFixture<CalculatePrivacyMetricComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [ CalculatePrivacyMetricComponent ]
    })
    .compileComponents();

    fixture = TestBed.createComponent(CalculatePrivacyMetricComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
