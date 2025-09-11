import { ComponentFixture, TestBed } from '@angular/core/testing';

import { GenomicComponent } from './genomic.component';

describe('GenomicComponent', () => {
  let component: GenomicComponent;
  let fixture: ComponentFixture<GenomicComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [ GenomicComponent ]
    })
    .compileComponents();

    fixture = TestBed.createComponent(GenomicComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
