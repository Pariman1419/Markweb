from mark_engine.documents.locate import build_folder_index, find_elr_folders


def test_folder_index_preserves_exact_annotated_range_and_cross_month(tmp_path):
    for month, name in [('7_JUL', 'ADI2607001'), ('8_AUG', 'ADI2607001 note'),
                        ('8_AUG', 'ADI2607001-03')]:
        (tmp_path / month / name).mkdir(parents=True)
    months = ['7_JUL', '8_AUG']
    expected = find_elr_folders(tmp_path, 'ADI2607001', months)
    index = build_folder_index(tmp_path, months)
    assert find_elr_folders(tmp_path, 'ADI2607001', months, index=index) == expected
