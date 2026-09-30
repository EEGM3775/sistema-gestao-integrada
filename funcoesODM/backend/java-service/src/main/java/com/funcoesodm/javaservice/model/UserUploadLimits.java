package com.funcoesodm.javaservice.model;

import jakarta.persistence.*;

@Entity
@Table(name = "user_upload_limits")
public class UserUploadLimits {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false, unique = true)
    private User user;

    @Column(name = "max_file_size_mb", nullable = false)
    private Integer maxFileSizeMb;

    @Column(name = "max_request_size_mb", nullable = false)
    private Integer maxRequestSizeMb;

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public User getUser() {
        return user;
    }

    public void setUser(User user) {
        this.user = user;
    }

    public Integer getMaxFileSizeMb() {
        return maxFileSizeMb;
    }

    public void setMaxFileSizeMb(Integer maxFileSizeMb) {
        this.maxFileSizeMb = maxFileSizeMb;
    }

    public Integer getMaxRequestSizeMb() {
        return maxRequestSizeMb;
    }

    public void setMaxRequestSizeMb(Integer maxRequestSizeMb) {
        this.maxRequestSizeMb = maxRequestSizeMb;
    }
}
